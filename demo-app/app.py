"""TableStory: clear, practical recipe discovery for everyday cooks."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, render_template

from recipe_api import create_recipe_blueprint, load_recipes

ROOT = Path(__file__).parent


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.update(TESTING=testing, COOKBOOK=set())
    recipes = load_recipes(ROOT)
    by_id = {recipe["id"]: recipe for recipe in recipes}
    app.register_blueprint(create_recipe_blueprint(recipes, app.config["COOKBOOK"]))

    @app.get("/")
    def index():
        return render_template("index.html", recipes=recipes)

    @app.get("/recipe/<recipe_id>")
    def detail(recipe_id: str):
        recipe = by_id.get(recipe_id)
        if not recipe:
            abort(404)
        return render_template("detail.html", recipe=recipe)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
