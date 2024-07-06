{ config
, lib
, dream2nix
, system
, ...
}:
let pyproject = lib.importTOML (config.mkDerivation.src + /pyproject.toml);
in {
  imports = [
    dream2nix.modules.dream2nix.pip
  ];

  deps = { nixpkgs, ... }: {
    python = nixpkgs.python312;
    inherit (nixpkgs) postgresql;
  };

  mkDerivation = {
    src = lib.cleanSourceWith {
      src = lib.cleanSource ./.;
      filter = name: type:
        !(builtins.any (x: x) [
          (lib.hasSuffix ".nix" name)
          (lib.hasPrefix "." (builtins.baseNameOf name))
          (lib.hasSuffix "flake.lock" name)
        ]);
    };
  };

  buildPythonPackage = {
    format = lib.mkForce "pyproject";
    pythonImportsCheck = [
      "symfexit"
    ];
  };

  name = "symfexit";
  version = "0.0.1";

  pip = {
    pypiSnapshotDate = builtins.readFile ./pip-snapshot-date.txt;
    requirementsFiles = [ "./requirements.txt" ];
    flattenDependencies = true;
    overrides.django.buildPythonPackage.makeWrapperArgs = [ "--set-default" "DJANGO_SETTINGS_MODULE" "symfexit.settings" ];
    # During the lockfile generation, we need tools from postgresql for the psycopg-c dependency of psycopg
    nativeBuildInputs = [ config.deps.postgresql ];
    overrides.psycopg-c = {
      imports = [ dream2nix.modules.dream2nix.nixpkgs-overrides ];
      nixpkgs-overrides.enable = true;
      mkDerivation.nativeBuildInputs = [ config.deps.postgresql ];
    };
  };
}
