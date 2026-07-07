"""Device connection resolution + on-site detection (data/fetch/network.py).

Pure functions over the committed device files (no network I/O), plus the
environment-override / FQDN branch of on_site_network with a patched hostname.
"""

from __future__ import annotations

import pytest

from magnetics.data.fetch import network, remote


# --- endpoint resolution from the `network` block -----------------------------
def test_diiid_mdsip_and_gateway_from_network_block():
    assert network.mdsip_address("diiid") == "atlas.gat.com:8000"
    assert network.gateway_address("diiid") == "cybele.gat.com:2039"


def test_diiid_cluster_login():
    login = network.cluster_login("diiid")
    assert login["host"] == "omega.gat.com"
    assert login["port"] == 22
    assert login["python"].endswith("toksearch_env/bin/python")


def test_nstx_endpoints_and_no_cluster():
    assert network.mdsip_address("nstx") == "skylark.pppl.gov:8501"
    assert network.gateway_address("nstx") == "flux.pppl.gov:22"
    # NSTX has no cluster block → host resolves to None (remote backend unused)
    assert network.cluster_login("nstx")["host"] is None


@pytest.mark.parametrize("safe", ["~/magnetics_fetch", "/scratch/u/fetch", "rel/dir", "~/a.b-c_d"])
def test_remote_dir_accepts_safe_paths(safe):
    assert remote._validate_remote_dir(safe) == safe


@pytest.mark.parametrize(
    "bad",
    ["~/my fetch", "$(touch x)", "a;b", "a&&b", "`id`", "a|b", "a>b", "-tmp", "--help"],
)
def test_remote_dir_rejects_shell_metacharacters_and_options(bad):
    with pytest.raises(ValueError):
        remote._validate_remote_dir(bad)


def test_run_remote_rejects_unsafe_remote_dir_before_commands(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("run_remote should validate remote_dir before subprocess")

    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    with pytest.raises(ValueError):
        remote.run_remote(184927, remote_dir="a;b")

    assert calls == []


# --- per-url duo / 2FA metadata -----------------------------------------------
def test_diiid_endpoints_do_not_need_duo():
    # key-based through cybele — explicitly marked duo:false on every endpoint
    assert network.needs_duo("diiid", "jump") is False
    assert network.needs_duo("diiid", "mdsip") is False
    assert network.needs_duo("diiid", "cluster") is False


def test_nstx_endpoints_need_duo():
    assert network.needs_duo("nstx", "jump") is True
    assert network.needs_duo("nstx", "mdsip") is True


def test_needs_duo_absent_defaults_true(monkeypatch):
    monkeypatch.setattr(network, "load_device", lambda device: {"network": {"jump": {}}})
    assert network.needs_duo("whatever", "jump") is True
    # a wholly unknown endpoint is also treated as needing 2FA
    assert network.needs_duo("whatever", "cluster") is True


# --- legacy flat gateway/server fallback --------------------------------------
def test_legacy_flat_keys_are_honored(monkeypatch):
    flat = {"gateway": "gw.example.org:2222", "server": "mds.example.org:8000"}
    monkeypatch.setattr(network, "load_device", lambda device: flat)
    assert network.gateway_address("whatever") == "gw.example.org:2222"
    assert network.mdsip_address("whatever") == "mds.example.org:8000"


# --- on_site_network: env override wins ---------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [("1", True), ("true", True), ("yes", True), ("0", False), ("", False), ("no", False)],
)
def test_on_site_env_override(monkeypatch, value, expected):
    monkeypatch.setenv("MAGNETICS_ON_NETWORK", value)
    # Override wins regardless of the actual hostname.
    monkeypatch.setattr(network.socket, "getfqdn", lambda: "somelaptop.local")
    assert network.on_site_network("diiid") is expected


# --- on_site_network: FQDN vs the device domain -------------------------------
def test_on_site_true_when_fqdn_in_site_domain(monkeypatch):
    monkeypatch.delenv("MAGNETICS_ON_NETWORK", raising=False)
    monkeypatch.setattr(network.socket, "getfqdn", lambda: "omega17.cluster.gat.com")
    assert network.on_site_network("diiid") is True


def test_on_site_false_for_a_laptop(monkeypatch):
    monkeypatch.delenv("MAGNETICS_ON_NETWORK", raising=False)
    monkeypatch.setattr(network.socket, "getfqdn", lambda: "my-macbook.lan")
    assert network.on_site_network("diiid") is False


def test_on_site_domain_is_device_specific(monkeypatch):
    """A DIII-D host is off-site for NSTX and vice versa (domains differ)."""
    monkeypatch.delenv("MAGNETICS_ON_NETWORK", raising=False)
    monkeypatch.setattr(network.socket, "getfqdn", lambda: "portal.pppl.gov")
    assert network.on_site_network("nstx") is True
    assert network.on_site_network("diiid") is False


@pytest.mark.skip(
    reason="Needs to run on a real GA host (cybele/omega) — can't be exercised "
    "off-site. Implement once we're running this on-site. Tracked in #48."
)
def test_on_site_detection_on_real_ga_host():
    """STUB — to implement when running on-site.

    Everything above mocks socket.getfqdn(), so it only tests the branch logic,
    never the real assumption: that an actual cybele/omega node reports a
    ``*.gat.com`` FQDN (fast, no reverse-DNS stall) and that the auto direct-TCP
    mdsip + no-ProxyJump paths connect. Those can only be validated by executing
    on the GA cluster; unskip and fill in when we have a real on-site test run.
    See issue #48.
    """
    raise NotImplementedError("validate on_site_network on a real cybele/omega host (#48)")
