{
  description = "Symfexit membersite";

  inputs = {
    dream2nix.url = "github:nix-community/dream2nix";
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/*.tar.gz";
  };

  outputs = inputs @ { self, nixpkgs, dream2nix, ... }:

    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs supportedSystems (system: (forSystem system f));

      forSystem = system: f: f rec {
        inherit system;
        linux-system = pkgs.lib.replaceStrings [ "darwin" ] [ "linux" ] system;
        pkgs = import nixpkgs { inherit system; overlays = [ ]; };
        pkgs-linux = import nixpkgs { system = linux-system; overlays = [ ]; };
        lib = pkgs.lib;
      };
    in
    {
      apps = forAllSystems ({ system, pkgs, ... }: {
        symfexit-docker = {
          type = "app";
          program = "${self.packages.${system}.symfexit-docker}";
        };
        symfexit-nginx = {
          type = "app";
          program = "${self.packages.${system}.symfexit-nginx}";
        };
      });

      packages = forAllSystems ({ system, linux-system, pkgs, pkgs-linux, ... }:
        let
          lib = pkgs.lib;
          symfexit-npm-deps = dream2nix.lib.evalModules {
            packageSets.nixpkgs = nixpkgs.legacyPackages.${system};
            modules = [
              ./theme.nix
              {
                paths.projectRoot = ./.;
                paths.projectRootFile = "flake.nix";
                paths.package = ./src/theme/static_src;
                paths.lockFile = "lock.${system}.json";
              }
            ];
          };
          theme-sources = pkgs.runCommand "theme-sources"
            {
              pythonSrc = lib.cleanSourceWith {
                src = lib.cleanSource ./.;
                filter = name: type:
                  !(builtins.any (x: x) [
                    (lib.hasSuffix ".nix" name)
                    (lib.hasPrefix "lock." (builtins.baseNameOf name))
                    (builtins.elem (builtins.baseNameOf name) [ "requirements.txt" "manifests" "pip-snapshot-date.txt" ])
                    (lib.hasPrefix "." (builtins.baseNameOf name))
                    (lib.hasSuffix "flake.lock" name)
                  ]);
              };
              node_modules = "${symfexit-npm-deps.config.package-func.result}/lib/node_modules/symfexit-base-theme/node_modules";
            } ''
            mkdir -p $out
            cp -r $pythonSrc/* $out
            chmod -R u+w $out
            cp -r $node_modules $out/src/theme/static_src/node_modules
          '';
          symfexit-base-theme = pkgs.runCommand "symfexit-base-theme"
            {
              src = theme-sources;
            } ''
            mkdir -p $out/staticfiles/css/dist
            export PATH=${pkgs.nodejs}/bin:$PATH
            cd $src/src/theme/static_src
            NODE_ENV=production ${pkgs.nodejs}/bin/npm run tailwindcss -- -i ./src/styles.css -o $out/staticfiles/css/dist/styles.css --minify
          '';
          symfexit-python = self.packages.${system}.symfexit-package.config.deps.python.withPackages (ps: with ps; [
            self.packages.${system}.symfexit-package.config.package-func.result
            uvicorn
          ]);
          linux-symfexit-python = self.packages.${linux-system}.symfexit-package.config.deps.python.withPackages (ps: with ps; [
            self.packages.${linux-system}.symfexit-package.config.package-func.result
            uvicorn
          ]);
          collectstatic = pkgs.runCommand "symfexit-staticfiles" { } ''
            # dummy secret key to be able to generate static files in production mode
            DJANGO_ENV=production SYMFEXIT_SECRET_KEY=dummy CONTENT_DIR=$(pwd) STATIC_ROOT=$out/staticfiles ${symfexit-python}/bin/django-admin collectstatic --noinput
          '';
        in
        rec {
          symfexit-package = dream2nix.lib.evalModules {
            packageSets.nixpkgs = nixpkgs.legacyPackages.${system};
            modules = [
              ./default.nix
              {
                paths.projectRoot = ./.;
                paths.projectRootFile = "flake.nix";
                paths.package = ./.;
                paths.lockFile = "lock.${system}.json";
              }
            ];
          };
          symfexit-staticfiles = pkgs.symlinkJoin {
            name = "symfexit-staticfiles";
            paths = [ symfexit-base-theme collectstatic ];
          };
          symfexit-docker = pkgs.dockerTools.streamLayeredImage {
            name = "symfexit";
            contents = pkgs.buildEnv {
              name = "symfexit-nginx";
              paths = with pkgs-linux.dockerTools; [
                self.packages.${linux-system}.symfexit-staticfiles
                (fakeNss.override {
                  extraGroupLines = [
                    "nogroup:x:65534:"
                  ];
                })
                binSh
                pkgs-linux.coreutils
              ];
              pathsToLink = [ "/staticfiles" "/etc" "/bin" "/var" ];
            };

            config = {
              Entrypoint = [
                (pkgs-linux.writeShellScript "entrypoint.sh" ''
                  if [ "$1" = "nginx" ]; then
                    mkdir -p {/tmp,/var/log/nginx}

                    ln -s /dev/stderr /var/log/nginx/error.log
                    ln -s /dev/stdout /var/log/nginx/access.log

                    shift
                    exec "${pkgs-linux.nginx}/bin/nginx" "-g" "daemon off;" "$@"
                  elif [ "$1" = "uvicorn" ]; then
                    shift
                    exec "${linux-symfexit-python}/bin/uvicorn" "$@"
                  elif [ "$1" = "django-admin" ]; then
                    shift
                    exec "${linux-symfexit-python}/bin/django-admin" "$@"
                  fi
                  exec "$@"
                '')
              ];
              Cmd = [ "uvicorn" "symfexit.asgi:application" ];
              ExposedPorts = { "8000/tcp" = { }; };
              Env = [
                "PATH=${pkgs-linux.nodejs}/bin:/bin"
                "NPM_COMMAND=${pkgs-linux.nodejs}/bin/npm"
                "THEME_SRC_DIR=${theme-sources}/src/theme/static_src"
                "DJANGO_ADMIN_COMMAND=${linux-symfexit-python}/bin/django-admin"
              ];
            };
          };
          symfexit-docker-tag = pkgs.writeShellScriptBin "symfexit-docker-tag" "echo ${symfexit-docker.imageTag}";
          relock-dependencies = pkgs.writeShellScriptBin "relock-dependencies" ''
            reporoot=$(git rev-parse --show-toplevel)
            cd $reporoot
            ${pkgs.coreutils}/bin/date "+%Y-%m-%d" > ./pip-snapshot-date.txt
            nix run .#symfexit-package.lock
            if [[ $(git diff --numstat | ${pkgs.gawk}/bin/awk '/lock\..*\.json$/ { print ($1 == $2 && $1 == 1) }') -eq 1 ]]; then
              # Only one line changed in lock.json, it's the invalidation hash which changed because of the date file
              git restore lock.*.json pip-snapshot-date.txt
              echo "Reset lock files and date file because only the invalidation hash changed"
            fi
          '';
        });

    };
}
