import sys

def test_peer_experts_stub():
    with open("strata-src/sycl/src/core/peer_experts.cpp", "r") as f:
        content = f.read()
    assert "is not ported to SYCL yet" in content, "Peer experts stub error message missing!"
    print("SUCCESS: Peer experts stub check passed.")

if __name__ == "__main__":
    test_peer_experts_stub()
