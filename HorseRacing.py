import os
import time
import requests
from tqdm import tqdm

DAY_1 = 86400
VERBOSE = False
INTERACTIVE = False
DATA_DIR = "data"


def read_constituents():
    with open("constituents.csv", "r") as f:
        lines = f.readlines()
    lines = [line.strip().split(",") for line in lines]
    return lines


def fetch_data(start, end):
    print("Reading list of symbols...")
    stocks = read_constituents()

    URL = "https://query1.finance.yahoo.com/v7/finance/download/{symbol}?period1={start}&period2={end}&interval=1d&events=history&includeAdjustedClose=true"

    print("Fetching data for {} stocks...".format(len(stocks)))
    for stock in tqdm(stocks[1:]):
        symbol = stock[0]
        formattedURL = URL.format(symbol=symbol, start=start, end=end)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
        }
        r = requests.get(formattedURL, headers=headers)
        with open("data/" + symbol + ".csv", "w") as f:
            f.write(r.text)

        # Rate limiting
        time.sleep(2)


def backtest(win_percent, loss_percent):
    # starting from the second day
    # list all of the stocks that opened 1% or more above the previous close
    # for each stock, calculate the daily return

    print("Getting list of symbols...")
    stocks = read_constituents()
    # read data from stocks
    data = {}
    for stock in tqdm(stocks[1:]):
        symbol = stock[0]
        data[symbol] = {}
        with open("data/" + symbol + ".csv", "r") as f:
            lines = f.readlines()
        stock_data = [line.strip().split(",") for line in lines]
        for line in stock_data[1:]:
            if "null" in line:
                continue
            data[symbol][line[0]] = {
                "open": float(line[1]),
                "high": float(line[2]),
                "low": float(line[3]),
                "close": float(line[4]),
                "adj_close": float(line[5]),
                "volume": float(line[6]),
            }

    print("Done.")

    # get first start date available
    start_date = min(data[symbol].keys())
    end_date = max(data[symbol].keys())

    start = convert_to_timestamp(start_date)
    end = convert_to_timestamp(end_date)

    results = []

    print("Running backtest...")
    pbar = tqdm(total=int((start - end) / DAY_1))
    while start < end:
        #  add a day
        start += DAY_1
        start_date = convert_to_date(start)
        # list each stock that opened 1% or more above the previous close
        horses = get_horses(stocks, data, start_date)
        # for each horse, calclate current current days return
        calculate_return(data, start_date, horses)
        # for each horse, calculate the total drawdown
        calculate_drawdown(data, start_date, horses)

        # if the horse has a return greater than 5%, and drawdown is less than 3%, add to winning horses
        winning_horses = get_winning_horses(
            win_percent, loss_percent, data, start_date, horses
        )

        # print the winning horses
        if VERBOSE:
            print_details(win_percent, data, start_date, horses, winning_horses)
            print("-" * 20)

        # if there were horses and some won, add to results
        if horses and winning_horses:
            results.append(1)
        elif horses and not winning_horses:
            results.append(0)

        if INTERACTIVE:
            # wait for user to continue
            input("Press Enter to continue...")
        else:
            pbar.update(1)
    pbar.close()

    # for each day that there were horses, how many days had winning horses?
    print("-" * 20)
    print("Results:")
    percent_of_days_with_winning_horses = round((sum(results) / len(results)) * 100, 2)
    print(f"{percent_of_days_with_winning_horses}% of days had winning horses")
    print("-" * 20)


def print_details(win_percent, data, start_date, horses, winning_horses):
    print(start_date)
    print("-" * 20)
    if horses:
        print("Stocks up by 1% in premarket:")
        for horse in horses:
            if start_date not in data[horse]:
                continue
            print(horse + ": " + str(data[horse][start_date]["preMarket"]) + " %")
    else:
        print("No stocks up by 1% in premarket")

    if winning_horses:
        print(f"Stocks went up {win_percent}% after opening:")
        for horse in winning_horses:
            if start_date not in data[horse]:
                continue
            print(horse + ": " + str(data[horse][start_date]["return"]) + " %")
    else:
        print(f"No stocks went up {win_percent}% after opening")
        print("Return of all stocks:")
        for horse in horses:
            if start_date not in data[horse]:
                continue
            print(horse + ": " + str(data[horse][start_date]["return"]) + " %")


def get_winning_horses(win_percent, loss_percent, data, start_date, horses):
    winning_horses = []
    for horse in horses:
        if start_date not in data[horse]:
            continue
        if (
            data[horse][start_date]["return"] > win_percent
            and data[horse][start_date]["drawdown"] < loss_percent
        ):
            winning_horses.append(horse)
    return winning_horses


def calculate_drawdown(data, start_date, horses):
    for horse in horses:
        if start_date not in data[horse]:
            continue
        current_open = data[horse][start_date]["open"]
        current_low = data[horse][start_date]["low"]
        current_drawdown = ((current_open - current_low) / current_open) * 100
        data[horse][start_date]["drawdown"] = round(current_drawdown, 2)


def calculate_return(data, start_date, horses):
    for horse in horses:
        if start_date not in data[horse]:
            continue
        current_open = data[horse][start_date]["open"]
        current_close = data[horse][start_date]["close"]
        current_return = ((current_close - current_open) / current_open) * 100
        data[horse][start_date]["return"] = round(current_return, 2)


def get_horses(stocks, data, start_date):
    horses = []
    for stock in stocks[1:]:
        symbol = stock[0]
        if start_date not in data[symbol]:
            continue
            # calculate the daily return
        start_timestamp = convert_to_timestamp(start_date)
        yesterday_timestamp = start_timestamp - DAY_1
        yesterday_date = convert_to_date(yesterday_timestamp)
        if yesterday_date in data[symbol]:
            previous_close = data[symbol][yesterday_date]["close"]
            current_open = data[symbol][start_date]["open"]
            if current_open > previous_close * 1.01:
                preMarket = ((current_open - previous_close) / previous_close) * 100
                data[symbol][start_date]["preMarket"] = round(preMarket, 2)
                horses.append(symbol)

    return horses


def get_dates():
    start_date = input(f"Please enter the start date (YYYY-MM-DD): ({default_start})")
    if not start_date:
        start_date = default_start
    # Ask for end date
    end_date = input(f"Please enter the end date (YYYY-MM-DD): ({default_end})")
    if not end_date:
        end_date = default_end
    return start_date, end_date


def convert_to_timestamp(date):
    return int(time.mktime(time.strptime(date, "%Y-%m-%d")))


def convert_to_date(timestamp):
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))


while True:
    default_start = "2017-03-24"
    default_end = "2022-03-25"
    # Ask user if they want to backtest or get data
    print("What would you like to do?")
    print("1. Get data")
    print("2. Backtest")
    print("3. Exit")

    # get user input
    user_input = input("Please enter your choice: ")

    if user_input == "1":
        # Ask for dates
        start_date, end_date = get_dates()
        # convert to timestamp
        start_timestamp = convert_to_timestamp(start_date)
        end_timestamp = convert_to_timestamp(end_date)
        fetch_data(start_timestamp, end_timestamp)
        print("Done!")

    elif user_input == "2":
        # check if data directory has at least one file
        if not os.listdir(DATA_DIR):
            print("No data found! Please fetch data first")
        # Get win percent and loss percent
        win_percent = input("Please enter the win percent: (5) ")
        if not win_percent:
            win_percent = 5
        loss_percent = input("Please enter the loss percent: (2) ")
        if not loss_percent:
            loss_percent = 2

        # Ask for verbosity level
        verbose = input("Display daily results? (y/n): (n) ")
        VERBOSE = verbose == "y"

        # Ask for interactive mode
        interactive = input("Interactive mode? (y/n): (n) ")
        INTERACTIVE = interactive == "y"

        backtest(
            win_percent,
            loss_percent,
        )

    elif user_input == "3":
        print("Goodbye!")
        break
