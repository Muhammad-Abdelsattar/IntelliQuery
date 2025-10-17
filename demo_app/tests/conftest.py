import pytest
from main import main

@pytest.fixture
def app():
    return main()
