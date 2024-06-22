{ config
, lib
, dream2nix
, ...
}:
let pyproject = lib.importTOML (config.mkDerivation.src + /pyproject.toml);
in {
  imports = [
    dream2nix.modules.dream2nix.pip
  ];

  deps = { nixpkgs, ... }: {
    python = nixpkgs.python312;
    psycopg-c = nixpkgs.python312Packages.psycopg.c;
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
    overrides.psycopg.mkDerivation.propagatedBuildInputs = [ config.deps.psycopg-c ];
  };
}
