"""
The mentor-facing pricing API.

Four modules, each with one job:

``mapping``
    The only translation between what a mentor answers and what the model is
    given, and the single source of the option lists the frontend renders.
``prediction``
    Loads both models once and turns one set of inputs into a price and a
    range.
``schemas``
    Request and response shapes, validated against the rules in ``mapping``.
``dependencies``
    Who is calling. One function, which is what will become authentication.
``app``
    The FastAPI application and its endpoints.
"""
