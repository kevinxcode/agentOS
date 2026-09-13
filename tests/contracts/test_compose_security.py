from pathlib import Path

import yaml


def test_only_web_publishes_a_production_port() -> None:
    model = yaml.safe_load(Path("compose.yaml").read_text())
    exposed = {
        name for name, service in model["services"].items() if service.get("ports")
    }
    assert exposed == {"web"}


def test_production_web_port_is_loopback_only() -> None:
    model = yaml.safe_load(Path("compose.yaml").read_text())
    ports = model["services"]["web"]["ports"]

    assert ports
    assert all(
        isinstance(port, dict) and port.get("host_ip") == "127.0.0.1"
        for port in ports
    )


def test_no_service_is_privileged_or_mounts_docker_socket() -> None:
    model = yaml.safe_load(Path("compose.yaml").read_text())
    for service in model["services"].values():
        assert service.get("privileged") is not True
        assert all(
            "/var/run/docker.sock" not in str(volume)
            for volume in service.get("volumes", [])
        )


def test_minio_images_use_approved_quay_release_pins() -> None:
    model = yaml.safe_load(Path("compose.yaml").read_text())

    assert model["services"]["minio"]["image"] == (
        "quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z"
    )
    assert model["services"]["minio-init"]["image"] == (
        "quay.io/minio/mc:RELEASE.2025-04-16T18-13-26Z"
    )
    for name in ("minio", "minio-init"):
        image = model["services"][name]["image"]
        assert image.startswith("quay.io/minio/")
        assert image.rsplit(":", maxsplit=1)[-1].startswith("RELEASE.")
