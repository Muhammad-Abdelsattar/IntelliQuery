import unittest
from main import main

class TestMain(unittest.TestCase):

    def test_main(self):
        try:
            main()
        except Exception as e:
            self.fail(f"main() raised an exception: {e}")

if __name__ == '__main__':
    unittest.main()
