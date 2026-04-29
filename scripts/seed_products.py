#!/usr/bin/env python3
"""Seed exactly 20 technology products with curated Unsplash images."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

BASE_PRODUCTS: list[dict[str, object]] = [
    {"name": "Laptop Pro 14", "description": "High-performance ultrabook for development and productivity.", "sku": "TECH-0001", "price": "1499.00", "stock": 35, "is_active": True, "image": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853"},
    {"name": "Laptop Air 13", "description": "Lightweight laptop with long battery life.", "sku": "TECH-0002", "price": "1199.00", "stock": 28, "is_active": True, "image": "https://images.unsplash.com/photo-1517336714739-489689fd1ca8"},
    {"name": "Smartphone Max 256GB", "description": "Premium smartphone with advanced camera and OLED display.", "sku": "TECH-0003", "price": "999.00", "stock": 50, "is_active": True, "image": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9"},
    {"name": "Smartphone Lite 128GB", "description": "Balanced phone for daily use and multimedia.", "sku": "TECH-0004", "price": "699.00", "stock": 65, "is_active": True, "image": "https://images.unsplash.com/photo-1598327105666-5b89351aff97"},
    {"name": "Monitor 27 4K", "description": "UHD monitor ideal for editing, office work, and gaming.", "sku": "TECH-0005", "price": "479.00", "stock": 22, "is_active": True, "image": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf"},
    {"name": "Monitor Curvo 34", "description": "Curved ultrawide display for multitasking and entertainment.", "sku": "TECH-0006", "price": "629.00", "stock": 15, "is_active": True, "image": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46"},
    {"name": "Mechanical Keyboard RGB", "description": "Mechanical keyboard with tactile switches and RGB lighting.", "sku": "TECH-0007", "price": "129.00", "stock": 70, "is_active": True, "image": "https://images.unsplash.com/photo-1587829741301-dc798b83add3"},
    {"name": "Wireless Keyboard Compact", "description": "Compact wireless keyboard for minimalist setups.", "sku": "TECH-0008", "price": "89.00", "stock": 55, "is_active": True, "image": "https://images.unsplash.com/photo-1541140532154-b024d705b90a"},
    {"name": "Gaming Mouse Pro", "description": "High-precision mouse with advanced optical sensor.", "sku": "TECH-0009", "price": "79.00", "stock": 85, "is_active": True, "image": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7"},
    {"name": "Wireless Mouse Silent", "description": "Silent ergonomic mouse for office and study.", "sku": "TECH-0010", "price": "49.00", "stock": 95, "is_active": True, "image": "https://images.unsplash.com/photo-1527814050087-3793815479db"},
    {"name": "Headphones Studio", "description": "Over-ear headphones for professional audio and mixing.", "sku": "TECH-0011", "price": "219.00", "stock": 42, "is_active": True, "image": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e"},
    {"name": "Gaming Headset 7.1", "description": "Surround headset with detachable microphone.", "sku": "TECH-0012", "price": "149.00", "stock": 37, "is_active": True, "image": "https://images.unsplash.com/photo-1484704849700-f032a568e944"},
    {"name": "Tablet Pro 11", "description": "Powerful tablet for creativity, reading, and productivity.", "sku": "TECH-0013", "price": "799.00", "stock": 33, "is_active": True, "image": "https://images.unsplash.com/photo-1561154464-82e9adf32764"},
    {"name": "Tablet Lite 10", "description": "Lightweight tablet for studying and media consumption.", "sku": "TECH-0014", "price": "429.00", "stock": 46, "is_active": True, "image": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0"},
    {"name": "Smartwatch Active", "description": "Smartwatch with health and fitness tracking.", "sku": "TECH-0015", "price": "299.00", "stock": 58, "is_active": True, "image": "https://images.unsplash.com/photo-1523275335684-37898b6baf30"},
    {"name": "Smartwatch Classic", "description": "Elegant smartwatch with notifications and GPS.", "sku": "TECH-0016", "price": "349.00", "stock": 40, "is_active": True, "image": "https://images.unsplash.com/photo-1434494878577-86c23bcb06b9"},
    {"name": "SSD NVMe 1TB", "description": "High-speed NVMe SSD for gaming and work.", "sku": "TECH-0017", "price": "139.00", "stock": 78, "is_active": True, "image": "https://images.unsplash.com/photo-1591488320449-011701bb6704"},
    {"name": "WiFi Router AX", "description": "WiFi 6 router for home and office with wide coverage.", "sku": "TECH-0018", "price": "189.00", "stock": 29, "is_active": True, "image": "https://images.unsplash.com/photo-1647427060118-4911c9821b82"},
    {"name": "Webcam Full HD", "description": "Webcam for video calls and high-definition streaming.", "sku": "TECH-0019", "price": "99.00", "stock": 52, "is_active": True, "image": "https://images.unsplash.com/photo-1587829741301-dc798b83add3"},
    {"name": "USB Microphone Pro", "description": "USB microphone for podcasting, streaming, and online classes.", "sku": "TECH-0020", "price": "159.00", "stock": 31, "is_active": True, "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc"},
    {"name": "Bluetooth Speaker Mini", "description": "Portable speaker with clear sound and extended battery life.", "sku": "TECH-0021", "price": "89.00", "stock": 60, "is_active": True, "image": "https://images.unsplash.com/photo-1589003077984-894e133dabab"},
    {"name": "Action Camera 4K", "description": "Durable compact camera for action recording.", "sku": "TECH-0022", "price": "249.00", "stock": 24, "is_active": True, "image": "https://images.unsplash.com/photo-1519183071298-a2962be96f83"},
    {"name": "Drone Explorer", "description": "Drone with stabilized camera and smart flight.", "sku": "TECH-0023", "price": "599.00", "stock": 18, "is_active": True, "image": "https://images.unsplash.com/photo-1473968512647-3e447244af8f"},
    {"name": "Power Bank 20000mAh", "description": "Fast-charging power bank for phones and tablets.", "sku": "TECH-0024", "price": "59.00", "stock": 80, "is_active": True, "image": "https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5"},
]


def build_image_pair(image_base: str) -> list[str]:
    first = f"{image_base}?auto=format&fit=crop&w=1200&h=1200&q=80"
    second = f"{image_base}?auto=format&fit=crop&w=1200&h=1200&crop=entropy&q=80"
    return [first, second]


PRODUCTS: list[dict[str, object]] = [
    {
        "name": item["name"],
        "description": item["description"],
        "sku": item["sku"],
        "price": item["price"],
        "stock": item["stock"],
        "is_active": item["is_active"],
        "images": build_image_pair(str(item["image"])),
    }
    for item in BASE_PRODUCTS
]


def post_json(url: str, payload: dict[str, object], timeout: int) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as exc:
        return 0, f"Network error: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed 24 tech products to API")
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1", help="API base URL")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    args = parser.parse_args()

    endpoint = f"{args.api_base.rstrip('/')}/products"
    created = 0
    failed = 0

    for payload in PRODUCTS:
        status, response_text = post_json(endpoint, payload, args.timeout)
        if 200 <= status < 300:
            created += 1
            print(f"[OK] {payload['sku']} - {payload['name']}")
        else:
            failed += 1
            print(f"[ERROR] {payload['sku']} status={status} response={response_text}")

    print(f"\nDone. created={created} failed={failed} total={len(PRODUCTS)}")


if __name__ == "__main__":
    main()
