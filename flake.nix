{
  description = "Finance transcript to mdBook workflow";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            bashInteractive
            jq
            just
            mdbook
          ];

          shellHook = ''
            echo "finance_ebook dev shell"
            if ! command -v gemini >/dev/null 2>&1; then
              echo "warning: gemini CLI not found in PATH; note generation will fail until it is installed."
            fi
          '';
        };
      });
}
