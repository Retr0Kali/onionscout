from onionscout.iocs import extract_iocs, merge_iocs

V3 = "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd"

SAMPLE = f"""
Contact us at admin@leaksite.onion or backup leak_support@proton.me.
Pay to BTC 1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2 or bech32 bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq.
ETH wallet 0x52908400098527886E0F7030069857D2E4169EE7.
Monero 48jewbNBQkNg3zGgawZ5Dbn3bRCxtCZH5V9Z3Qhv1VBtySTTAmKtVdFqtA7NuJ7c4N4b1cBwP5p4XMo9xJq3sNv7VZ6s9zt
Mirror: http://{V3}.onion/leak
Server at 185.220.101.5 was compromised via CVE-2024-3400 and cve-2023-1234.
"""


def test_extracts_crypto_wallets():
    iocs = extract_iocs(SAMPLE)
    assert "0x52908400098527886E0F7030069857D2E4169EE7" in iocs.eth
    assert any(b.startswith("1BvBM") for b in iocs.btc)
    assert any(b.startswith("bc1q") for b in iocs.btc)
    assert len(iocs.xmr) == 1


def test_extracts_emails_onions_ips_cves():
    iocs = extract_iocs(SAMPLE)
    assert "leak_support@proton.me" in iocs.emails
    assert f"{V3}.onion" in iocs.onions
    assert "185.220.101.5" in iocs.ipv4
    assert "CVE-2024-3400" in iocs.cves
    assert "CVE-2023-1234" in iocs.cves  # case-normalised


def test_pgp_block_and_fingerprint():
    text = (
        "-----BEGIN PGP PUBLIC KEY BLOCK-----\nabc\n"
        "Fingerprint: AAAA BBBB CCCC DDDD EEEE FFFF 0000 1111 2222 3333"
    )
    iocs = extract_iocs(text)
    assert iocs.pgp_keys == 1
    assert "AAAABBBBCCCCDDDDEEEEFFFF000011112222333" in "".join(iocs.pgp_fingerprints)


def test_merge_dedupes_across_sets():
    a = extract_iocs("mail x@y.com and CVE-2024-0001")
    b = extract_iocs("mail x@y.com and CVE-2024-0002")
    merged = merge_iocs([a, b])
    assert merged.emails == ["x@y.com"]
    assert set(merged.cves) == {"CVE-2024-0001", "CVE-2024-0002"}


def test_total_counts_everything():
    iocs = extract_iocs(SAMPLE)
    assert iocs.total >= 8
    assert iocs.as_dict()["crypto"]["eth"]
