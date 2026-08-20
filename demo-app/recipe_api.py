"""Recipe-domain API shared by the migration and final TableStory app."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, request


def load_recipes(root: Path) -> list[dict]:
    return json.loads((root / "recipes.json").read_text())


def recipe_matches(recipe: dict, query: str) -> bool:
    searchable = " ".join([
        recipe["title"], recipe["description"], recipe["category"],
        *recipe["dietary_tags"], *recipe["ingredients"],
    ]).lower()
    return query.strip().lower() in searchable


def create_recipe_blueprint(recipes: list[dict], cookbook: set[str]) -> Blueprint:
    blueprint = Blueprint("recipes", __name__)
    by_id = {recipe["id"]: recipe for recipe in recipes}

    @blueprint.get("/api/recipes")
    def recipes_api():
        query = request.args.get("q", "")
        return jsonify([recipe for recipe in recipes if recipe_matches(recipe, query)])

    @blueprint.get("/api/recipes/<recipe_id>")
    def recipe_api(recipe_id: str):
        recipe = by_id.get(recipe_id)
        return jsonify(recipe) if recipe else (jsonify({"error": "Recipe not found"}), 404)

    @blueprint.get("/api/cookbook")
    def get_cookbook():
        return jsonify([recipe for recipe in recipes if recipe["id"] in cookbook])

    @blueprint.post("/api/cookbook")
    def add_cookbook():
        recipe_id = (request.get_json(silent=True) or {}).get("id")
        if recipe_id not in by_id:
            return jsonify({"error": "Unknown recipe"}), 400
        cookbook.add(recipe_id)
        return jsonify({"ids": sorted(cookbook)}), 201

    @blueprint.delete("/api/cookbook/<recipe_id>")
    def remove_cookbook(recipe_id: str):
        cookbook.discard(recipe_id)
        return jsonify({"ids": sorted(cookbook)})

    @blueprint.get("/api/rails")
    def rails_api():
        def ids(predicate):
            return [recipe["id"] for recipe in recipes if predicate(recipe)][:8]

        return jsonify([
            {"title": "Popular this week", "recipe_ids": ids(lambda recipe: recipe["featured"])},
            {"title": "Ready in 30 minutes", "recipe_ids": ids(lambda recipe: recipe["prep_minutes"] + recipe["cook_minutes"] <= 30)},
            {"title": "Vegetarian favourites", "recipe_ids": ids(lambda recipe: "Vegetarian" in recipe["dietary_tags"])},
            {"title": "My Cookbook", "recipe_ids": ids(lambda recipe: recipe["id"] in cookbook)},
        ])

    return blueprint
