{ config
, lib
, dream2nix
, system
, ...
}:
{
  imports = [
    dream2nix.modules.dream2nix.nodejs-package-lock-v3
    dream2nix.modules.dream2nix.nodejs-granular-v3
  ];

  deps = { nixpkgs, ... }: {
    python = nixpkgs.python312;
    inherit (nixpkgs) postgresql;
  };

  mkDerivation = {
    src = lib.cleanSourceWith {
      src = lib.cleanSource ./src/theme/static_src;
      filter = name: type:
        !(builtins.any (x: x) [
          (lib.hasSuffix ".nix" name)
          (lib.hasPrefix "." (builtins.baseNameOf name))
          (lib.hasSuffix "flake.lock" name)
        ]);
    };
  };

  nodejs-package-lock-v3 = {
    packageLockFile = "${config.mkDerivation.src}/package-lock.json";
  };

  name = "symfexit-base-theme";
  version = "0.0.1";
}
