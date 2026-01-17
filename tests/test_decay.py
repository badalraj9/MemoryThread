import unittest
from memory_thread.services.decay_engine import DecayEngine

class TestDecayEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DecayEngine()

    def test_calculate_freshness(self):
        # Identity: No decay
        f = self.engine.calculate_freshness(1.0, 365, "identity")
        self.assertEqual(f, 1.0)

        # Event: Fast decay (0.1)
        # 10 days: 1.0 * e^(-0.1 * 10) = e^-1 = 0.367
        f = self.engine.calculate_freshness(1.0, 10, "event")
        self.assertAlmostEqual(f, 0.367, places=2)

        # Fact: Slow decay (0.001)
        # 100 days: e^-0.1 = 0.90
        f = self.engine.calculate_freshness(1.0, 100, "fact")
        self.assertAlmostEqual(f, 0.904, places=2)

if __name__ == '__main__':
    unittest.main()
