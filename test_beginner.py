import unittest

from beginner import backtest


class BeginnerBacktestTest(unittest.TestCase):
    def test_both_signals_use_previous_close_and_charge_each_side(self):
        days = [(0, 10, 10), (1, 10, 10), (2, 10, 12),
                (3, 20, 8), (4, 15, 100)]
        for indicator, signal in [("ma", 11), ("roc", 20)]:
            trades, equity = backtest(days, indicator, 2)
            self.assertEqual([(t[0], t[1], t[2]) for t in trades],
                             [(3, "買入", 20), (4, "賣出", 15)])
            self.assertAlmostEqual(trades[0][3], signal)
            self.assertAlmostEqual(equity, 10000 - 499 * 20.0285 + 499 * 15 * 0.995575)
            _, held = backtest(days[:4], indicator, 2)
            self.assertAlmostEqual(held, 10000 - 499 * 20.0285 + 499 * 8 * 0.995575)

    def test_btc_allows_fractional_coins_and_charges_crypto_fees(self):
        days = [(0, 90000, 90000), (1, 90000, 90000), (2, 90000, 110000),
                (3, 100000, 80000), (4, 120000, 120000)]
        trades, equity = backtest(days, "ma", 2, crypto=True)
        self.assertEqual([t[1] for t in trades], ["買入", "賣出"])
        self.assertAlmostEqual(equity, 10000 / 100100 * 119880)
