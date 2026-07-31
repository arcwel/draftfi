#!/usr/bin/env bash
# Create a stable, self-signed code-signing identity for local DraftFi builds.
#
# Why this exists: macOS grants keychain access per *code signature*. PyInstaller
# ad-hoc signs, and an ad-hoc signature's hash changes with the binary, so every
# rebuild looked like a different application and macOS re-prompted for access to
# the stored API key. Signing every build with one stable identity makes the
# grant stick — approve the prompt once, never again.
#
# This is NOT an Apple Developer certificate. It does not satisfy Gatekeeper or
# notarization; first launch still needs right-click -> Open. It only stabilises
# the signature so the keychain stops re-asking.
#
# Run once:  bash packaging/make_signing_identity.sh
# No administrator password is required — everything happens in the current
# user's keychain and trust domain.
set -euo pipefail

NAME="${DRAFTFI_SIGN_IDENTITY:-DraftFi Local Signing}"

# `find-identity -v` lists an untrusted certificate too, tagging it
# CSSMERR_TP_NOT_TRUSTED. Matching on the name alone therefore reported "nothing
# to do" for exactly the broken state this script exists to fix. Check the tag.
EXISTING="$(security find-identity -v -p codesigning | grep "$NAME" || true)"
if [ -n "$EXISTING" ]; then
  if printf '%s' "$EXISTING" | grep -q "CSSMERR"; then
    echo "Identity '$NAME' exists but is not trusted — repairing trust only."
    CERT="$(mktemp)"
    security find-certificate -c "$NAME" -p > "$CERT"
    security add-trusted-cert -r trustRoot -p codeSign "$CERT"
    rm -f "$CERT"
    security find-identity -v -p codesigning | grep "$NAME"
    exit 0
  fi
  echo "Identity '$NAME' already exists and is trusted — nothing to do."
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# extendedKeyUsage=codeSigning is the bit that makes the cert usable by codesign;
# basicConstraints CA:false keeps it a leaf certificate.
cat > "$WORK/openssl.cnf" <<CNF
[ req ]
distinguished_name = dn
x509_extensions    = v3
prompt             = no
[ dn ]
CN = $NAME
[ v3 ]
basicConstraints       = critical,CA:false
keyUsage               = critical,digitalSignature
extendedKeyUsage       = critical,codeSigning
subjectKeyIdentifier   = hash
CNF

openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout "$WORK/key.pem" -out "$WORK/cert.pem" -config "$WORK/openssl.cnf" >/dev/null 2>&1

# OpenSSL 3 defaults to a PKCS#12 MAC that macOS's `security` cannot read
# ("MAC verification failed during PKCS12 import"). The legacy algorithms below
# are what makes the bundle importable. A throwaway password is used because
# empty ones are also unreliable through `security import`.
P12PASS="draftfi-temp-$$"
openssl pkcs12 -export -inkey "$WORK/key.pem" -in "$WORK/cert.pem" \
  -out "$WORK/identity.p12" -passout "pass:$P12PASS" -name "$NAME" \
  -macalg sha1 -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES \
  2>/dev/null || \
openssl pkcs12 -export -legacy -inkey "$WORK/key.pem" -in "$WORK/cert.pem" \
  -out "$WORK/identity.p12" -passout "pass:$P12PASS" -name "$NAME"

KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

# -T /usr/bin/codesign pre-authorises codesign to use the private key, so builds
# don't stop to ask. -A would authorise everything; deliberately not used.
security import "$WORK/identity.p12" -k "$KEYCHAIN" -P "$P12PASS" \
  -T /usr/bin/codesign -T /usr/bin/security >/dev/null

# codesign refuses an untrusted identity (CSSMERR_TP_NOT_TRUSTED), so this step
# is REQUIRED, not optional.
#
# It goes in the USER trust domain, not the admin one. The difference matters:
#
#   security add-trusted-cert -d ... -k /Library/Keychains/System.keychain
#
# writes to the admin domain, needs sudo, and asks for an administrator
# password. Dropping -d writes the same trust setting to the current user's
# trust domain instead — and that is all codesign consults when deciding
# whether to accept an identity for signing. No sudo, no password, no dialog.
#
# The narrower domain is also the correct one on the merits: this certificate
# only ever signs this user's local builds, so trusting it machine-wide would
# grant more than the job needs.
echo
echo "Trusting the certificate for code signing (current user only)…"
security add-trusted-cert -r trustRoot -p codeSign "$WORK/cert.pem" || {
  echo
  echo "Trust step did not complete. The identity exists but codesign will"
  echo "refuse it, so builds stay ad-hoc signed and macOS will keep asking for"
  echo "keychain access after every rebuild. Re-run this script to retry."
  exit 1
}

# Stop the keychain prompting on every signing operation.
security set-key-partition-list -S apple-tool:,apple:,codesign: \
  -s -k "" "$KEYCHAIN" >/dev/null 2>&1 || true

echo
security find-identity -v -p codesigning | grep "$NAME" || true
echo "Done. Rebuild with: backend/.venv/bin/python packaging/build.py"
