"""Test OCI reference parsing with full tag."""

from stowk8s.strategies.helm_template import _collect_images


def test_collect_oci_reference_with_full_tag() -> None:
    """
    Ensure that an OCI reference with a compound tag is parsed correctly.
    """
    # Mock a chart that returns the OCI reference via an annotation.
    chart_data = {
        "name": "test-chart",
        "annotations": {
            # The annotation is a JSON string as the chart would emit it.
            "helm.sh/images": '[{"name": "us-east1-docker.pkg.dev/vmw-app-catalog/hosted-registry-f00e7443adc/containers/photon-5/os-shell", "tag": "5-photon-5-r83"}]'
        },
    }

    # Use the same helper that the strategy calls.
    doc = {
        "kind": "Deployment",
        "metadata": {"name": "my-deploy"},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "image": "us-east1-docker.pkg.dev/vmw-app-catalog/hosted-registry-f00e7443adc/containers/photon-5/os-shell:5-photon-5-r83"
                        }
                    ]
                }
            }
        },
    }
    images = _collect_images([doc])
    # Only one image should be found.
    assert len(images) == 1
    img = images[0]
    assert img.image_name.startswith("oci://"), "OCI prefix missing"
    assert img.image_tag == "5-photon-5-r83", f"Expected full tag, got '{img.image_tag}'"
    assert img.full_reference == "oci://us-east1-docker.pkg.dev/vmw-app-catalog/hosted-registry-f00e7443adc/containers/photon-5/os-shell:5-photon-5-r83"