import json

from app import app
from app.tasks import add, check, mult, save_state
from app.tappable import tappable
from app.utils import deserialize_chain

tappable_operation = tappable(
    (add.s(6) | mult.s(16)), check.s(), save_state.s()
)

@app.route('/')
def index():
    tappable_operation(4)
    return 'hello world'

@app.route('/resume')
def resume():
    with open('chains.json') as f:
        t_chain = json.load(f)
    deserialize_chain(t_chain)(10)
    return 'on it'
