{ lib
, stdenv
, fetchFromGitHub
, python3
, nodejs
, rustPlatform
, pkg-config
, webkitgtk
, gtk3
, glib
, makeWrapper
}:

let
  pname = "halbert";
  version = "0.1.1";

  # Python environment with dependencies
  pythonEnv = python3.withPackages (ps: with ps; [
    fastapi
    uvicorn
    httpx
    requests
    psutil
    pydantic
    pyyaml
    numpy
    # chromadb and sentence-transformers need special handling
  ]);

in stdenv.mkDerivation rec {
  inherit pname version;

  src = fetchFromGitHub {
    owner = "halbert-ai";
    repo = "halbert";
    rev = "v${version}";
    sha256 = lib.fakeSha256;
  };

  nativeBuildInputs = [
    nodejs
    rustPlatform.cargoSetupHook
    pkg-config
    makeWrapper
  ];

  buildInputs = [
    webkitgtk
    gtk3
    glib
    pythonEnv
  ];

  buildPhase = ''
    # Build frontend
    cd halbert_core/halbert_core/dashboard/frontend
    npm install
    npm run build
    
    # Build Tauri
    cd src-tauri
    cargo build --release
    cd ../../../../..
  '';

  installPhase = ''
    mkdir -p $out/bin $out/lib/halbert $out/share/applications
    
    # Install Tauri binary
    install -Dm755 halbert_core/halbert_core/dashboard/frontend/src-tauri/target/release/halbert \
      $out/bin/halbert
    
    # Install Python package
    cp -r halbert_core/halbert_core $out/lib/halbert/
    
    # Create wrapper for Python backend
    makeWrapper ${pythonEnv}/bin/python $out/bin/halbert-api \
      --add-flags "-m halbert_core.dashboard" \
      --prefix PYTHONPATH : "$out/lib/halbert"
    
    # Desktop file
    cat > $out/share/applications/halbert.desktop << EOF
    [Desktop Entry]
    Name=Halbert
    Comment=AI-Powered System Administration Assistant
    Exec=$out/bin/halbert
    Icon=halbert
    Terminal=false
    Type=Application
    Categories=System;Utility;
    EOF
  '';

  meta = with lib; {
    description = "AI-powered system administration assistant";
    homepage = "https://github.com/halbert-ai/halbert";
    license = licenses.mit;
    maintainers = [ ];
    platforms = platforms.linux;
  };
}
