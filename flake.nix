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

      packages = forAllSystems ({ system, linux-system, pkgs, ... }: rec {
        symfexit-package = dream2nix.lib.evalModules {
          packageSets.nixpkgs = nixpkgs.legacyPackages.${system};
          modules = [
            ./default.nix
            {
              paths.projectRoot = ./.;
              # can be changed to ".git" or "flake.nix" to get rid of .project-root
              paths.projectRootFile = "flake.nix";
              paths.package = ./.;
            }
          ];
        };
        symfexit-staticfiles = pkgs.runCommand "symfexit-staticfiles" { } ''
          DJANGO_ENV=production STATIC_ROOT=$out ${symfexit-python}/bin/django-admin collectstatic --noinput
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
      });

    };
}
