import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from coherence import is_degenerate, response_text, is_degenerate_response

class TestCoherence(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(is_degenerate(""))
        self.assertTrue(is_degenerate("   "))
        self.assertTrue(is_degenerate(None))

    def test_punct_run(self):
        self.assertTrue(is_degenerate("!" * 20))
        self.assertTrue(is_degenerate("?????"))
        self.assertTrue(is_degenerate("...????..."))

    def test_repeated_words(self):
        self.assertTrue(is_degenerate("a b a b a b a b a b a b"))  # low unique ratio
        self.assertTrue(is_degenerate("the the the the the the"))
        self.assertFalse(is_degenerate("hello world this is a normal sentence with plenty of different words"))

    def test_single_char_repeats(self):
        self.assertTrue(is_degenerate("x" * 20))
        self.assertFalse(is_degenerate("short"))

    def test_normal(self):
        self.assertFalse(is_degenerate("Hello, this is a coherent response with normal words."))

    def test_response_text_extraction(self):
        self.assertEqual(response_text({"content": "hi"}), "hi")
        self.assertEqual(response_text({"reasoning_content": "think"}), "think")
        self.assertEqual(response_text({"text": "text"}), "text")
        self.assertEqual(response_text({"content": "", "reasoning_content": "fallback"}), "fallback")
        self.assertEqual(response_text({}), "")
        self.assertEqual(response_text(None), "")

    def test_is_degenerate_response(self):
        self.assertTrue(is_degenerate_response({"content": "!!!!!!!!!!"}))
        self.assertTrue(is_degenerate_response({"reasoning_content": "!!!!!!!!!!"}))
        self.assertFalse(is_degenerate_response({"content": "Normal answer."}))

if __name__ == "__main__":
    unittest.main()


class TestDetectDegenerate(unittest.TestCase):
    def setUp(self):
        from coherence import detect_degenerate
        self.dd = detect_degenerate

    def test_clean(self):
        self.assertIsNone(self.dd("Quantum computing uses qubits."))
        self.assertIsNone(self.dd("The capital of France is Paris."))

    def test_artifact(self):
        self.assertIsNotNone(self.dd("!" * 20))
        self.assertIsNotNone(self.dd("hello" + "!" * 10))

    def test_repeated_word(self):
        self.assertIsNotNone(self.dd("the " * 20))

    def test_empty(self):
        self.assertIsNotNone(self.dd(""))
        self.assertIsNotNone(self.dd(None))

    def test_excessive_punct(self):
        self.assertIsNotNone(self.dd("a" + "?" * 30))


if __name__ == "__main__":
    unittest.main()
