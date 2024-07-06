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
        lib = pkgs.lib;
      };
    in
    {
      apps = forAllSystems ({ system, pkgs, ... }: {
        symfexit-docker = {
          type = "app";
          program = "${self.packages.${system}.symfexit-docker}";
        };
      });

      packages = forAllSystems ({ system, linux-system, pkgs, ... }: rec {
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
        symfexit-staticfiles = pkgs.runCommand "symfexit-staticfiles" { } ''
          # dummy secret key to be able to generate static files in production mode
          DJANGO_ENV=production SYMFEXIT_SECRET_KEY=dummy CONTENT_DIR=$(pwd) STATIC_ROOT=$out ${symfexit-python}/bin/django-admin collectstatic --noinput
        '';
        symfexit-python = symfexit-package.config.deps.python.withPackages (ps: with ps; [
          symfexit-package.config.package-func.result
          uvicorn
        ]);
        symfexit-docker = pkgs.dockerTools.streamLayeredImage {
          name = "symfexit";
          config = {
            Entrypoint = [ "${self.packages.${linux-system}.symfexit-python}/bin/uvicorn" "symfexit.asgi:application" ];
            ExposedPorts = { "8000/tcp" = { }; };
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
