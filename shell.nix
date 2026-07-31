{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "crisc-analysis-env";
  
  buildInputs = [
    pkgs.python3
    pkgs.python3Packages.pandas
    pkgs.python3Packages.chess
    pkgs.python3Packages.duckdb
    pkgs.python3Packages.plotly
  ];

  shellHook = ''
    export PS1="\[\e[1;32m\][crisc-analysis-env:\w]\$\[\e[0m\] "
    echo "Environment Ready! Python, Pandas, Chess, DuckDB, and Plotly are loaded."
  '';
}