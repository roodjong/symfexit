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
        pkgs = import nixpkgs { inherit system; overlays = [ ]; };
        lib = pkgs.lib;
      };
    in
    {

      packages = forAllSystems ({ system, pkgs, ... }: rec {
        symfexit-package = dream2nix.lib.evalModules {
          packageSets.nixpkgs = inputs.dream2nix.inputs.nixpkgs.legacyPackages.${system};
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
        symfexit-python = symfexit-package.config.deps.python.withPackages (ps: with ps; [
          symfexit-package.config.package-func.result
          uvicorn
        ]);
      });

    };
}
