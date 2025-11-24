from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Category, Order, OrderItem, Product, ProductReview


def product_list(request):
    products = Product.objects.all()
    categories = Category.objects.all()

    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    sort = request.GET.get("sort", "-created_at").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    if category_id:
        products = products.filter(category_id=category_id)

    # Sorting options
    if sort == "price_asc":
        products = products.order_by("price")
    elif sort == "price_desc":
        products = products.order_by("-price")
    else:
        # default: newest first
        products = products.order_by("-created_at")

    context = {
        "products": products,
        "categories": categories,
        "current_query": query,
        "current_category": category_id,
        "current_sort": sort,
    }
    return render(request, "store/product_list.html", context)


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        name = request.POST.get("name", "").strip() or "Anonymous"
        try:
            rating = int(request.POST.get("rating", "0"))
        except ValueError:
            rating = 0
        comment = request.POST.get("comment", "").strip()

        if 1 <= rating <= 5:
            ProductReview.objects.create(
                product=product,
                name=name,
                rating=rating,
                comment=comment,
            )

    reviews = product.reviews.all()

    return render(
        request,
        "store/product_detail.html",
        {
            "product": product,
            "reviews": reviews,
        },
    )


def _get_cart(session):
    return session.setdefault("cart", {})


def cart_detail(request):
    cart = _get_cart(request.session)
    product_ids = cart.keys()
    products = Product.objects.filter(id__in=product_ids)

    items = []
    total = Decimal("0.00")

    products_by_id = {str(p.id): p for p in products}

    for product_id, item in cart.items():
        product = products_by_id.get(product_id)
        if not product:
            continue
        quantity = item.get("quantity", 1)
        price = Decimal(str(product.price))
        line_total = price * quantity
        total += line_total
        items.append(
            {
                "product": product,
                "quantity": quantity,
                "line_total": line_total,
            }
        )

    return render(
        request,
        "store/cart.html",
        {"items": items, "total": total},
    )


def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk)
    cart = _get_cart(request.session)

    product_id = str(product.id)
    item = cart.get(product_id, {"quantity": 0})
    item["quantity"] = item.get("quantity", 0) + 1
    cart[product_id] = item

    request.session.modified = True
    return redirect("cart_detail")


def remove_from_cart(request, pk):
    cart = _get_cart(request.session)
    product_id = str(pk)
    if product_id in cart:
        del cart[product_id]
        request.session.modified = True
    return redirect("cart_detail")


def update_cart_quantity(request, pk):
    if request.method != "POST":
        return redirect("cart_detail")

    cart = _get_cart(request.session)
    product_id = str(pk)
    try:
        quantity = int(request.POST.get("quantity", "1"))
    except ValueError:
        quantity = 1

    if quantity <= 0:
        if product_id in cart:
            del cart[product_id]
    else:
        item = cart.get(product_id, {"quantity": 0})
        item["quantity"] = quantity
        cart[product_id] = item

    request.session.modified = True
    return redirect("cart_detail")


def checkout(request):
    cart = _get_cart(request.session)
    if not cart:
        return redirect("product_list")

    product_ids = cart.keys()
    products = Product.objects.filter(id__in=product_ids)
    products_by_id = {str(p.id): p for p in products}

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        address = request.POST.get("address", "").strip()
        city = request.POST.get("city", "").strip()
        postal_code = request.POST.get("postal_code", "").strip()

        if not all([full_name, email, address, city, postal_code]):
            error = "Please fill in all required fields."
            return render(
                request,
                "store/checkout.html",
                {"cart": cart, "products": products_by_id, "error": error},
            )

        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            full_name=full_name,
            email=email,
            address=address,
            city=city,
            postal_code=postal_code,
        )

        for product_id, item in cart.items():
            product = products_by_id.get(product_id)
            if not product:
                continue
            quantity = item.get("quantity", 1)
            OrderItem.objects.create(
                order=order,
                product=product,
                price=product.price,
                quantity=quantity,
            )

        request.session["cart"] = {}
        request.session.modified = True

        return redirect("order_confirmation", order_id=order.id)

    return render(
        request,
        "store/checkout.html",
        {"cart": cart, "products": products_by_id},
    )


def order_confirmation(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    return render(request, "store/order_confirmation.html", {"order": order})


@login_required
def profile_view(request):
    orders = request.user.orders.all().order_by("-created_at")
    return render(
        request,
        "store/profile.html",
        {
            "user_obj": request.user,
            "orders": orders,
        },
    )


def signup_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created and logged in.")
            return redirect("product_list")
    else:
        form = UserCreationForm()

    return render(request, "store/signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "Logged in successfully.")
            return redirect("product_list")
    else:
        form = AuthenticationForm(request)

    return render(request, "store/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("product_list")
