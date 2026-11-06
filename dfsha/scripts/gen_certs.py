"""Identidades por servicio. Dos CA: transporte de aplicación y catálogo etcd.

La CA de etcd solo emite certificados para sus miembros y los coordinadores.
Los clientes/nodos nunca reciben una credencial de acceso al catálogo ni la KEK.
"""
import argparse
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def public(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)


def generate(output):
    out = Path(output)
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Directorio no vacío: no se reemplazan identidades/llaves existentes.')
    out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    def name(cn):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    def write(path, data, private=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if private:
            os.chmod(path, 0o600)
    def ca(cn):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder().subject_name(name(cn)).issuer_name(name(cn))
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(minutes=1)).not_valid_after(now + dt.timedelta(days=365))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), True).sign(key, hashes.SHA256()))
        write(out/'private'/f'{cn}.key', pem_key(key), True)
        return key, cert
    app_key, app_ca = ca('app-ca')
    etcd_key, etcd_ca = ca('etcd-ca')
    def identity(role, ca_key, ca_cert, prefix='node'):
        key = ec.generate_private_key(ec.SECP256R1())
        names = [x509.DNSName(f'{role}.dfsha.internal'), x509.DNSName(role),
                 x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]
        if role in ('meta1', 'meta2'):
            names.append(x509.DNSName('meta.dfsha.internal'))
        cert = (x509.CertificateBuilder().subject_name(name(role)).issuer_name(ca_cert.subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(minutes=1)).not_valid_after(now + dt.timedelta(days=90))
                .add_extension(x509.SubjectAlternativeName(names), False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH,
                                                      ExtendedKeyUsageOID.CLIENT_AUTH]), False)
                .sign(ca_key, hashes.SHA256()))
        write(out/role/f'{prefix}.key', pem_key(key), True)
        write(out/role/f'{prefix}.crt', cert.public_bytes(serialization.Encoding.PEM))
    caps, auth = ed25519.Ed25519PrivateKey.generate(), ed25519.Ed25519PrivateKey.generate()
    receipts = {f'dn{i}': ed25519.Ed25519PrivateKey.generate() for i in range(1, 5)}
    for role in ['meta1', 'meta2', 'dn1', 'dn2', 'dn3', 'dn4', 'cliente']:
        identity(role, app_key, app_ca)
        write(out/role/'ca.crt', app_ca.public_bytes(serialization.Encoding.PEM))
        write(out/role/'capability.pub', public(caps))
        if role.startswith('meta'):
            identity(role, etcd_key, etcd_ca, 'etcd')
            write(out/role/'etcd-ca.crt', etcd_ca.public_bytes(serialization.Encoding.PEM))
            write(out/role/'auth.key', pem_key(auth), True)
            write(out/role/'auth.pub', public(auth))
            write(out/role/'capability.key', pem_key(caps), True)
            write(out/role/'receipts.json', json.dumps({k: public(v).decode() for k, v in receipts.items()}).encode())
        elif role in receipts:
            write(out/role/'receipt.key', pem_key(receipts[role]), True)
    for role in ('etcd1', 'etcd2', 'etcd3'):
        identity(role, etcd_key, etcd_ca)
        write(out/role/'ca.crt', etcd_ca.public_bytes(serialization.Encoding.PEM))
    print('Identidades generadas en', out, '(private/ no se despliega).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='certs')
    generate(parser.parse_args().output)
