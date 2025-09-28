{
  description = "0x42-cogs - Discord Red Bot Cogs";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonPackages = pkgs.python311Packages;
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Python and tools
            (python311.withPackages (ps: with ps; [
              discordpy
              aiohttp
              typing-extensions
              pytest
              black
              isort
              mypy
              openai
              tiktoken
              httpx
              tenacity
            ]))
          ];

          shellHook = ''
            echo "Welcome to 0x42-cogs development environment!"
            echo "Python version: $(python --version)"
          '';
        };

        packages.default = pythonPackages.buildPythonPackage {
          pname = "0x42-cogs";
          version = "0.1.1";
          src = ./.;
          
          propagatedBuildInputs = with pythonPackages; [
            discordpy
            aiohttp
            typing-extensions
            kubernetes
            openai
            tiktoken
            httpx
            tenacity
          ];
          
          doCheck = false;  # Disable tests for now
          
          meta = with pkgs.lib; {
            description = "Utility cogs for Discord Red Bot";
            homepage = "https://github.com/0x4272616E646F6E/0x42-cogs";
            license = licenses.mit;
            maintainers = [ "0x4272616E646F6E" ];
          };
        };
      }
    );
}
