"""Accounts / Categories / Rules CRUD e2e。"""
import pytest


# === Categories ===

def test_categories_list_root_only_default(logged_in_client):
    """默认登录时 seed 已建分类树,顶级分类应 ≥ 2。"""
    resp = logged_in_client.get("/api/categories")
    assert resp.status_code == 200
    items = resp.json()["items"]
    # 顶级分类(parent_id=None)从 seed 来,应 ≥ 6
    assert isinstance(items, list)


def test_create_update_delete_category(logged_in_client):
    create = logged_in_client.post("/api/categories", json={
        "name": "测试分类一", "kind": "expense", "parent_id": None, "sort_order": 999,
    })
    assert create.status_code == 201
    cid = create.json()["id"]

    upd = logged_in_client.patch(f"/api/categories/{cid}", json={"name": "改名后"})
    assert upd.status_code == 200
    assert upd.json()["name"] == "改名后"

    delete = logged_in_client.delete(f"/api/categories/{cid}")
    assert delete.status_code == 204


def test_create_subcategory(logged_in_client):
    parent = logged_in_client.post("/api/categories", json={
        "name": "父类2026", "kind": "expense", "parent_id": None,
    }).json()
    child = logged_in_client.post("/api/categories", json={
        "name": "子类2026", "kind": "expense", "parent_id": parent["id"],
    })
    assert child.status_code == 201
    assert child.json()["parent_id"] == parent["id"]


# === Accounts ===

def test_accounts_crud(logged_in_client):
    create = logged_in_client.post("/api/accounts", json={
        "name": "工行储蓄卡 9999", "type": "bank_debit",
        "institution": "工商银行", "last4": "9999", "currency": "CNY",
    })
    assert create.status_code == 201
    aid = create.json()["id"]

    list_ = logged_in_client.get("/api/accounts")
    assert any(a["id"] == aid for a in list_.json()["items"])

    upd = logged_in_client.patch(f"/api/accounts/{aid}",
        json={"name": "工行储蓄卡 9999 (改名)"})
    assert upd.status_code == 200
    assert "(改名)" in upd.json()["name"]

    archive = logged_in_client.patch(f"/api/accounts/{aid}", json={"archived": True})
    assert archive.status_code == 200
    assert archive.json()["archived"] is True


def test_account_create_validates_last4(logged_in_client):
    resp = logged_in_client.post("/api/accounts", json={
        "name": "x", "type": "bank_debit",
        "institution": "Y", "last4": "abcd", "currency": "CNY",
    })
    assert resp.status_code == 422


# === Rules ===

def test_rules_crud_with_marker(logged_in_client):
    """marker 规则 category_id=None 必须可创建(spec § 7.1)。"""
    create = logged_in_client.post("/api/rules", json={
        "pattern": "测试marker-2026", "match_kind": "contains",
        "category_id": None, "priority": 25,
    })
    assert create.status_code == 201
    rid = create.json()["id"]
    assert create.json()["category_id"] is None

    upd = logged_in_client.patch(f"/api/rules/{rid}", json={"priority": 30})
    assert upd.status_code == 200
    assert upd.json()["priority"] == 30

    delete = logged_in_client.delete(f"/api/rules/{rid}")
    assert delete.status_code == 204


def test_rules_list_ordered_by_priority(logged_in_client):
    resp = logged_in_client.get("/api/rules")
    assert resp.status_code == 200
    items = resp.json()["items"]
    priorities = [r["priority"] for r in items]
    assert priorities == sorted(priorities)


def test_all_endpoints_require_login(client):
    for path in ["/api/categories", "/api/accounts", "/api/rules"]:
        assert client.get(path).status_code == 401
