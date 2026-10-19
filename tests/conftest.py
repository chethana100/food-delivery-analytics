import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db  # noqa: E402


class Builder:
    """Tiny helper for hand-built fixtures so each test states its own numbers."""

    def __init__(self):
        self.conn = db.connect(":memory:")
        db.create_schema(self.conn)
        self.conn.execute("INSERT INTO customers VALUES ('C1','Test One'),('C2','Test Two')")
        self._oid = self._iid = 0

    def product(self, pid, name, brand="B1", ptype="Burgers"):
        self.conn.execute("INSERT INTO products VALUES (?,?,?,?)", (pid, name, brand, ptype))

    def order(self, when, items, customer="C1", area="North", status="Delivered"):
        """items: list of dicts(product, qty, price, cost, disc=0, refund=0, ret=0)."""
        self._oid += 1
        self.conn.execute("INSERT INTO orders VALUES (?,?,?,?,?)",
                          (self._oid, f"{when} 12:00:00", customer, area, status))
        for it in items:
            self._iid += 1
            self.conn.execute(
                "INSERT INTO order_items VALUES (?,?,?,?,?,?,?,?,?)",
                (self._iid, self._oid, it["product"], it["qty"], it["price"],
                 it.get("disc", 0), it.get("refund", 0), it.get("ret", 0), it["cost"]))
        self.conn.commit()
        return self._oid


@pytest.fixture
def b():
    return Builder()
