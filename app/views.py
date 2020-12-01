from app import app
from app.tasks import add, check, mult
from app.tappable import tappable

tappable_operation = tappable(
        (add.s(6) | mult.s(16)), check.s()
    )

@app.route('/')
def index():
    print(tappable_operation(4))
    return 'hello world'
