"""Homólogo de src/KitchenSink/Restaurant.cs y Restaurants.cs."""
import random
from dataclasses import dataclass

DESCRIPTION = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed egestas gravida nibh, "
    "quis porttitor felis venenatis id. Nam sodales mollis quam eget venenatis. Aliquam metus "
    "lorem, tincidunt ut egestas imperdiet, convallis lacinia tortor."
)

_RESTAURANTS = [
    ("Cheesecake Factory", "American"), ("University Cafe", "American"), ("Slider Bar", "American"),
    ("Shokolaat", "American"), ("Gordon Biersch", "American"), ("Crepevine", "American"),
    ("Creamery", "American"), ("Old Pro", "American"), ("Nola's", "Cajun"),
    ("House of Bagels", "Bagels"), ("The Prolific Oven", "Sandwiches"), ("La Strada", "Italian"),
    ("Buca di Beppo", "Italian"), ("Pasta?", "Italian"), ("Madame Tam", "Asian"),
    ("Sprout Cafe", "Salad"), ("Pluto's", "Salad"), ("Junoon", "Indian"),
    ("Bistro Maxine", "French"), ("Three Seasons", "Vietnamese"), ("Sancho's Taquira", "Mexican"),
    ("Reposado", "Mexican"), ("Siam Royal", "Thai"), ("Krung Siam", "Thai"), ("Thaiphoon", "Thai"),
    ("Tamarine", "Vietnamese"), ("Joya", "Tapas"), ("Jing Jing", "Chinese"),
    ("Patxi's Pizza", "Pizza"), ("Evvia Estiatorio", "Mediterranean"), ("Cafe 220", "Mediterranean"),
    ("Cafe Renaissance", "Mediterranean"), ("Kan Zeman", "Mediterranean"),
    ("Gyros-Gyros", "Mediterranean"), ("Mango Caribbean Cafe", "Caribbean"),
    ("Coconuts Caribbean Restaurant & Bar", "Caribbean"), ("Rose & Crown", "English"),
    ("Baklava", "Mediterranean"), ("Mandarin Gourmet", "Chinese"), ("Bangkok Cuisine", "Thai"),
    ("Darbar Indian Cuisine", "Indian"), ("Mantra", "Indian"), ("Janta", "Indian"),
    ("Hyderabad House", "Indian"), ("Starbucks", "Coffee"), ("Peet's Coffee", "Coffee"),
    ("Coupa Cafe", "Coffee"), ("Lytton Coffee Company", "Coffee"), ("Il Fornaio", "Italian"),
    ("Lavanda", "Mediterranean"), ("MacArthur Park", "American"),
    ("St Michael's Alley", "Californian"), ("Cafe Renzo", "Italian"), ("Osteria", "Italian"),
    ("Vero", "Italian"), ("Cafe Renzo", "Italian"), ("Miyake", "Sushi"), ("Sushi Tomo", "Sushi"),
    ("Kanpai", "Sushi"), ("Pizza My Heart", "Pizza"), ("New York Pizza", "Pizza"),
    ("California Pizza Kitchen", "Pizza"), ("Round Table", "Pizza"), ("Loving Hut", "Vegan"),
    ("Garden Fresh", "Vegan"), ("Cafe Epi", "French"), ("Tai Pan", "Chinese"),
]


@dataclass(frozen=True)
class Restaurant:
    description: str
    rating: int
    name: str
    cuisine: str


def get_all_restaurants() -> list[Restaurant]:
    # random.Next(0, 6) en C# -> randint(0, 5)
    return [Restaurant(DESCRIPTION, random.randint(0, 5), n, c) for n, c in _RESTAURANTS]
