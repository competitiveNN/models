import sys

def test_peer_experts_implemented():
    with open("strata-src/sycl/src/core/peer_experts.cpp", "r") as f:
        content = f.read()
    # The stub message must be gone - the SYCL port should be implemented
    assert "not ported to SYCL yet" not in content, "Peer experts still stubbed - SYCL port not implemented!"
    assert "not available in the SYCL build" not in content, "Peer experts launch/finish still stubbed!"
    # Key SYCL port functions must be present
    assert "bool PeerExperts::open" in content, "PeerExperts::open not implemented!"
    assert "bool PeerExperts::launch" in content, "PeerExperts::launch not implemented!"
    assert "bool PeerExperts::finish" in content, "PeerExperts::finish not implemented!"
    assert "sycl::malloc_host" in content or "sycl::malloc_device" in content, "SYCL memory allocation not used!"
    print("SUCCESS: Peer experts SYCL port is implemented.")

if __name__ == "__main__":
    test_peer_experts_implemented()
