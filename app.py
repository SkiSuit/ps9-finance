import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    # I will display the shares table using jinja syntax:

    # Load shares table
    shares = db.execute("SELECT * FROM shares WHERE user_id=(?) order BY total_price DESC", session["user_id"])
    # Load current cash amount to be displayed:
    cash = db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])
    # Find total value in shares
    total = 0
    for share in shares:
        total += float(share["total_price"])

    # Return appropriate values to the html page
    return render_template("portfolio.html", shares=shares, cash=usd(cash[0]["cash"]), total=usd(total + cash[0]["cash"]))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        # Handle share count inut:
        if not request.form.get("shares"):
            return apology("must provide share amount TBP", 403)
        elif (request.form.get("shares").isnumeric() == False):
            return apology("amount must be numerical")
        elif (int(request.form.get("shares")) < 0):
            return apology("can only purchase 1 or more shares")
        # Handle symbol type input:
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 403)
        else:
            # This means they provided a symbol
            # we should now check for it via lookup.
            stock = lookup(request.form.get("symbol"))
            if isinstance(stock, dict) == False:
                return apology("Inputed symbol does not exist :(")
            else:
                # If we got here the stock exists, we can try and complete the transaction
                # Get stocks price
                # Get users balance
                balance = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
                share_count = request.form.get("shares")
                if (float(balance[0]["cash"]) - (float(share_count) * float(stock["price"])) > 0):
                    # If we got here, the user has enough money to complete the transaction

                    # Save date:
                    now = datetime.now()
                    time = now.strftime("%d/%m/%Y %H:%M:%S")

                    # I need to subtract the corrosponding money amount from the users cash column in data base
                    # Subtract from the total net gain of the transaction a 1% commission rate
                    total_price = ((float(share_count) * float(stock["price"])))
                    # I will also subtract a 1% commision for every buy transaction made.
                    db.execute("INSERT INTO stocks (user_id, stock_symbol, count, price, total_price, time, method) VALUES(?, ?, ?, ?, ?, ?, ?)",
                               session["user_id"], stock["symbol"], share_count, stock["price"], total_price, time, "buy")

                    # Update shares TABLE:
                    stock_type = db.execute(
                        "select stock_symbol from stocks WHERE user_id =(?) and method = (?) GROUP BY stock_symbol", session["user_id"], "buy")
                    table_shares = db.execute(
                        "select stock_symbol from shares WHERE user_id =(?) GROUP BY stock_symbol", session["user_id"])
                    # Firstly ill add all new stocks:
                    for type in stock_type:
                        price = lookup(type["stock_symbol"])
                        # Check if the share is in the table.
                        if len(table_shares) > 0:
                            # This means it is not the first time we buy
                            # We need to check if type["stock_symbol" is in the shares list
                            if not any(dictionary["stock_symbol"] == type["stock_symbol"] for dictionary in table_shares):
                                db.execute("INSERT INTO shares (user_id, stock_symbol,price, shares, total_price) VALUES (?,?,?,?,?)",
                                           session["user_id"], type["stock_symbol"], usd(price["price"]), 0, 0)
                                # we found that the value does not exist so we can add to shares table
                        else:
                            # This is the first time we buy, we can just inseret
                            db.execute("INSERT INTO shares (user_id, stock_symbol,price, shares, total_price) VALUES (?,?,?,?,?)",
                                       session["user_id"], type["stock_symbol"], usd(price["price"]), 0, 0)

                    stocks = db.execute("select * from stocks WHERE user_id =(?) AND method = (?)", session["user_id"], "buy")
                    for s in stocks:
                        price = lookup(type["stock_symbol"])
                        # For every purchase made, i will add the amount of stock purchased and incrumnet the total counter
                        # We also need to only use new buys, so we will keep track of purchases using a global variable
                        tracker = db.execute("SELECT * FROM tracker where user_id = (?)", session["user_id"])
                        if (int(s["id"]) > tracker[0]["stock_id"]):
                            # this cheks the tracker TABLE
                            # updating the shares TABLE
                            db.execute("UPDATE shares SET shares = shares + (?), total_price = total_price + (?) WHERE user_id = (?) and stock_symbol = (?)", int(
                                s["count"]), s["total_price"], session["user_id"], s["stock_symbol"])
                            # Updating the share TABLE for visuals for the index
                            for_visual = db.execute("SELECT * FROM shares WHERE user_id =(?) and stock_symbol = (?)",
                                                    session["user_id"], s["stock_symbol"])
                            db.execute("UPDATE shares SET visual_total=(?) WHERE user_id =(?) and stock_symbol = (?)",
                                       usd(for_visual[0]["total_price"]), session["user_id"], s["stock_symbol"])
                            # Updating tracker TABLE
                            db.execute("UPDATE tracker SET stock_id = (?) WHERE user_id = (?)", s["id"], session["user_id"])
                            # This dict saves the latets id for a transaction for an individual.

                    # Update balance:
                    cash_finale = balance[0]["cash"] - (total_price)
                    db.execute("UPDATE users SET cash = (?) WHERE id = (?)", cash_finale, session["user_id"])
                    return redirect("/")
                else:
                    return apology("Not enough money in acc to complete the transaction")
    else:
        # If we get here the rquest was a GET, this means we should show quote.html:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    stocks = db.execute("SELECT * FROM stocks WHERE user_id = (?)", session["user_id"])
    # I need to pass stocks to history.html
    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)
        else:
            # This means they provided a symbol
            # we should now check for it via lookup.
            stock = lookup(request.form.get("symbol"))
            if isinstance(stock, dict) == True:
                # If we got here the stock exists, we can display it on quoted using jinja.

                return render_template("quoted.html", name=stock["symbol"], price=usd(float(stock["price"])))
            else:
                return apology("Inputed symbol does not exist :(")
    else:
        # If we get here the rquest was a GET, this means we should show quote.html:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # I need to add an extension register html page, allowing user to input username and password.
    # I need to submit user input via post to register
    # User must enter values to both fields, password must be 6 charcahters long
    # If the un exists in db I prompt for a new one.
    # If un does not exist in db i can add the new one to it
    # i need to save a hash of the users passward, using generate_passward_hash, to the data base
    # I need to redirect back to homepage

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        if not request.form.get("confirmation"):
            return apology("must provide confirmation", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        # If username exists, we prompt fot a new one.
        if len(rows) > 0:
            return apology("username already exists")

        else:
            # Check for upper case characters
            conditionC = False  # Conditon for capiral charachters
            conditionN = False  # Conditon for numeric values charachters
            for char in request.form.get("password"):
                if char.isupper() == True:
                    conditionC = True
                elif char.isnumeric() == True:
                    conditionN = True

            # Check password length:
            if (len(request.form.get("password")) < 6):
                return apology("password not long enough")
            elif (conditionC == False):
                return apology("password must contain al least 1 upper case character")
            elif (conditionN == False):
                return apology("password must contain al least 1 number")
            if not request.form.get("password") == request.form.get("confirmation"):
                return apology("Passwords did not match")

            # Save password to database using hash:
            hashed_ps = generate_password_hash(request.form.get("password"))

            # Insert username and password to database
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), hashed_ps)

            id = db.execute("SELECT id FROM users WHERE username = (?) and hash = (?)", request.form.get("username"), hashed_ps)
            # Add user id to dictionary of stocks
            db.execute("INSERT INTO tracker (user_id, stock_id) VALUES (?,?)", id[0]["id"], 0)

        # Auto log in after register:
        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    else:
        # If we got here, the method is GET
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    shares = db.execute("SELECT * FROM shares WHERE user_id = (?)", session["user_id"])
    condition = False
    if request.method == "POST":
        # For POST requests, process the data and try to validate sell

        if not request.form.get("symbol"):
            # If submited without picking symbol:
            return apology("must pick a stock")
        else:
            for share in shares:
                if (request.form.get("symbol") == share["stock_symbol"]):
                    # If we got here the user actually owns this stock. we need to find out if the user owns enough
                    # We will set condition to be true so we can check for stock amount.
                    condition = True

        if not request.form.get("shares"):
            # If submited without picking symbol:
            return apology("must pick a stock")

        elif (request.form.get("shares").isnumeric() == True) and (int(request.form.get("shares")) > 0):
            # Iif we got here, our value is a number greater then 0, we can check wether the user has enough shares in their account
            if (condition == True):
                # We only check if we actually have some of the desired stock
                for share in shares:
                    if (share["stock_symbol"] == request.form.get("symbol")):
                        # If we found the row of the matching symbol:
                        price = lookup(request.form.get("symbol"))
                        profit = float(price["price"]) * float(request.form.get("shares"))
                        new_count = int(share["shares"]) - int(request.form.get("shares"))
                        new_total_price = float(new_count * float(price["price"]))
                        # Save date:
                        now = datetime.now()
                        time = now.strftime("%d/%m/%Y %H:%M:%S")

                        if (int(share["shares"]) >= int(request.form.get("shares"))):
                            # The user has enough shares in order to sell their desired amount
                            # we need to sell the stock for curent price
                            # we will subtract the amount of bought share from count for the stock symbol for the user
                            db.execute("UPDATE shares SET shares = (?),price = (?), total_price = (?), visual_total = (?) WHERE user_id = (?) AND stock_symbol = (?)", new_count, usd(
                                price["price"]), new_total_price, usd(new_total_price), session["user_id"], request.form.get("symbol"))
                            # Update stocks TABLE:
                            # Save date:
                            db.execute("INSERT INTO stocks (user_id, stock_symbol, count, price, total_price, time, method) VALUES (?,?, ?, ?, ?, ?, ?)", session["user_id"], share["stock_symbol"], int(
                                request.form.get("shares")), price["price"], (price["price"] * int(request.form.get("shares"))), time, "sell")
                            # we will add the profit to cash in users
                            # I will also
                            db.execute("UPDATE users SET cash = cash + (?) WHERE id =(?)", profit, session["user_id"])
                            return redirect("/")

                        else:
                            return apology("You don`t own enough shares")
            else:
                condition = False
                return apology("You don`t own enough shares")
        else:
            # If we got here the share amount exists but is not a number greater then 0]
            return apology("Share count not valid.")
    else:
        # For GET requests, render the sell page
        return render_template("sell.html", shares=shares)
