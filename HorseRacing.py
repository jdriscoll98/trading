import json
import os
from pprint import pprint
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


def fetch_data(start, end, candle_size):
    print("Reading list of symbols...")
    stocks = read_constituents()

    if candle_size == "D":
        URL = "https://query1.finance.yahoo.com/v7/finance/download/{symbol}?period1={start}&period2={end}&interval=1d&events=history&includeAdjustedClose=true"
        fetch_daily_data(start, end, stocks, URL)
    elif candle_size == "H":
        # get access key from secerts.json
        try:
            with open("secrets.json", "r") as f:
                secrets = f.read()
            secrets = json.loads(secrets)
            api_key = secrets["api_key"]
        except FileNotFoundError:
            print("Could not find secrets.json file")
            return
        except KeyError:
            print("Could not find access_key in secrets.json")
            return

        URL = "https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval=30min&outputsize=full&apikey={api_key}"
        print("Fetching data...")
        num = 1
        for stock in tqdm(stocks[1:]):
            symbol = stock[0]
            formattedURL = URL.format(symbol=symbol, api_key=api_key)
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
            }
            r = requests.get(formattedURL, headers=headers)
            # Create data folder if it doesn't exist
            if not os.path.exists(DATA_DIR):
                os.makedirs(DATA_DIR)

            if not os.path.exists(DATA_DIR + "/intraday"):
                os.makedirs(DATA_DIR + "/intraday")

            with open(DATA_DIR + "/" + "intraday" + "/" + symbol + ".csv", "w") as f:
                f.write(r.text)

            num += 1
            if num % 75 == 0:
                time.sleep(60)


def fetch_daily_data(start, end, stocks, URL):
    print("Fetching daily data for {} stocks...".format(len(stocks)))
    for stock in tqdm(stocks[1:]):
        symbol = stock[0]
        formattedURL = URL.format(symbol=symbol, start=start, end=end)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
        }
        r = requests.get(formattedURL, headers=headers)
        # Create data folder if it doesn't exist
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            os.makedirs(DATA_DIR + "/daily")
        with open(DATA_DIR + "/" + "daily" + "/" + symbol + ".csv", "w") as f:
            f.write(r.text)

        # Rate limiting
        time.sleep(2)


def backtest(win_percent, loss_percent, threshold):
    # starting from the second day
    # list all of the stocks that opened 1% or more above the previous close
    # for each stock, calculate the daily return

    print("Getting list of symbols...")
    stocks = read_constituents()
    # read data from stocks
    daily_data = {}
    hourly_data = {}
    for stock in tqdm(stocks[1:]):
        symbol = stock[0]
        daily_data[symbol] = {}
        with open("data/daily/" + symbol + ".csv", "r") as f:
            lines = f.readlines()
        stock_data = [line.strip().split(",") for line in lines]

        for line in stock_data[1:]:
            if "null" in line:
                continue
            daily_data[symbol][line[0]] = {
                "open": float(line[1]),
                "high": float(line[2]),
                "low": float(line[3]),
                "close": float(line[4]),
                "adj_close": float(line[5]),
                "volume": float(line[6]),
            }

        if not daily_data.get(symbol):
            continue

        # calculate the total volume of the stock
        total_volume = 0
        for value in daily_data[symbol].values():
            total_volume += value["volume"]

        # calculate the average daily volume
        average_volume = total_volume / len(daily_data[symbol])

        # if average volume is below 5 million then skip
        if average_volume < 7500000:
            daily_data.pop(symbol)
            continue

        with open("data/intraday/" + symbol + ".csv", "r") as f:
            data = f.read()
        data = json.loads(data)
        data = data.get("Time Series (30min)")
        if not data:
            continue

        hourly_data[symbol] = {}
        for timestamp in data:
            if hourly_data[symbol].get(timestamp[:10]) is None:
                hourly_data[symbol][timestamp[:10]] = {}
            hourly_data[symbol][timestamp[:10]][timestamp[11:]] = {
                "open": float(data[timestamp]["1. open"]),
                "high": float(data[timestamp]["2. high"]),
                "low": float(data[timestamp]["3. low"]),
                "close": float(data[timestamp]["4. close"]),
                "volume": float(data[timestamp]["5. volume"]),
            }

    stocks = [[key] for key in daily_data.keys()]
    print(stocks, len(stocks))

    # get first start date available
    symbol = stocks[0][0]
    start_date = min(hourly_data[symbol].keys())
    end_date = max(hourly_data[symbol].keys())

    start = convert_to_timestamp(start_date)
    end = convert_to_timestamp(end_date)

    results = []

    print("Running backtest...")
    pbar = tqdm(total=int((start - end) / DAY_1))
    num_of_days = 0
    while start < end:
        num_of_days += 1
        #  add a day
        start += DAY_1
        start_date = convert_to_date(start)
        # list each stock that opened 1% or more above the previous close
        horses = get_horses(stocks, daily_data, start_date)
        # for each horse, calclate current current days return
        calculate_return(daily_data, hourly_data, start_date, horses)
        # for each horse, calculate the total drawdown
        calculate_drawdown(daily_data, start_date, horses)
        # for each horse, calculate the first hour's return
        calculate_first_hour(start_date, hourly_data, horses)

        potential_horses = get_potential_horses(
            start_date, hourly_data, horses, threshold
        )
        winning_horses = get_winning_horses(
            win_percent,
            loss_percent,
            daily_data,
            hourly_data,
            start_date,
            potential_horses,
        )

        # calculate total gain of winning horses
        total_return = 0
        for horse in winning_horses:
            total_return += daily_data[horse][start_date]["return"]
        # calculate average return
        average_return = total_return / len(winning_horses) if winning_horses else 0
        losing_horses = list(set(potential_horses) - set(winning_horses))

        # calculate total loss of losing horses
        total_loss = 0
        for horse in losing_horses:
            total_loss += daily_data[horse][start_date]["return"]
        # calculate average loss
        average_loss = total_loss / len(losing_horses) if losing_horses else 0

        # print the winning horses
        if VERBOSE:
            print_details(
                win_percent,
                daily_data,
                hourly_data,
                start_date,
                horses,
                potential_horses,
                winning_horses,
                average_return,
                threshold,
            )
            print("-" * 20)

        # if there were horses and some won, add to results
        if potential_horses and winning_horses:
            result = "win"
        elif potential_horses and not winning_horses:
            result = "loss"
        else:
            result = "no_horses"

        results.append(
            {
                "result": result,
                "num_of_winning_horses": len(winning_horses),
                "percent_of_winners": len(winning_horses) / len(potential_horses)
                if potential_horses
                else 100,
                "average_return_of_winners": average_return,
                "average_return_of_losers": average_loss,
                "num_of_losing_horses": len(losing_horses),
            }
        )

        if INTERACTIVE:
            # wait for user to continue
            input("Press Enter to continue...")
        else:
            pbar.update(1)
    pbar.close()

    # for each day that there were horses, how many days had winning horses?
    print("-" * 20)
    print("Results:")
    print("From: {}".format(min(hourly_data[symbol].keys())))
    print("To: {}".format(end_date))

    potential_days = sum([1 for result in results if result["result"] != "no_horses"])
    percent_of_days_with_potential_horses = round(
        (potential_days / len(results)) * 100, 2
    )
    print(
        "Percent of days with potential horses: {}%".format(
            percent_of_days_with_potential_horses
        )
    )
    winning_days = sum([1 for result in results if result["result"] == "win"])
    percent_of_days_with_winning_horses = round(
        (winning_days / potential_days) * 100, 2
    )
    print(
        "Percent of potential days with winning horses: {}%".format(
            percent_of_days_with_winning_horses
        )
    )

    average_daily_percent_of_winning_horses = round(
        (
            sum(
                [
                    results["percent_of_winners"]
                    for results in results
                    if results["result"] == "win"
                ]
            )
            / potential_days
        ),
        2,
    )
    print(
        "Average daily percent of winning horses: {}%".format(
            average_daily_percent_of_winning_horses * 100
        )
    )

    print("-" * 20)

    average_return_of_winning_horses = sum(
        [
            result["average_return_of_winners"]
            for result in results
            if result["result"] == "win"
        ]
    ) / sum(
        [
            result["num_of_winning_horses"]
            for result in results
            if result["result"] == "win"
        ]
    )
    average_return_of_losing_horses = sum(
        [
            result["average_return_of_losers"]
            for result in results
            if result["result"] != "no_horses"
        ]
    ) / sum(
        [
            result["num_of_losing_horses"]
            for result in results
            if result["result"] != "no_horses"
        ]
    )
    print(
        "Average return of winning horses: {}%".format(average_return_of_winning_horses)
    )
    print(
        "Average return of losing horses: {}%".format(average_return_of_losing_horses)
    )

    # TODO: calculate win rate of how many times a winning horse actually won ( stocks that go up 1% in the first hour and then go up 4% by the rest of the day)
    print("-" * 20)


def print_details(
    win_percent,
    data,
    hourly_data,
    start_date,
    horses,
    potential_horses,
    winning_horses,
    average_return,
    threshold,
):
    print(start_date)
    print("-" * 20)
    if horses:
        print("Stocks up by 1% in premarket: ({}/{})".format(len(horses), len(horses)))
        for horse in horses:
            if start_date not in data[horse]:
                continue
            print(horse + ": " + str(data[horse][start_date]["preMarket"]) + " %")
    else:
        print("No stocks up by 1% in premarket")

    if potential_horses:
        print(
            "Stocks up by {}% in the first hour: ({}/{})".format(
                threshold, len(potential_horses), len(horses)
            )
        )
        for horse in potential_horses:
            if start_date not in data[horse]:
                continue
            print(
                horse
                + ": "
                + str(hourly_data[horse][start_date]["first_hour_return"])
                + " %"
            )
    else:
        print("No stocks up by {}% in the first hour".format(threshold))
    if winning_horses:
        print(
            f"Stocks went up {win_percent}% after opening: ({len(winning_horses)}/{len(horses)})"
        )
        for horse in winning_horses:
            if start_date not in data[horse]:
                continue
            print(horse + ": " + str(data[horse][start_date].get("return")) + " %")
        print("Average return of winning horses: {}%".format(average_return))
    else:
        print(f"No stocks went up {win_percent}% after opening")


def get_potential_horses(start_date, hourly_data, horses, threshold):
    potential_horses = []
    for horse in horses:
        if horse not in hourly_data:
            continue
        if start_date not in hourly_data[horse]:
            continue
        if hourly_data[horse][start_date]["first_hour_return"] > threshold:
            potential_horses.append(horse)
    return potential_horses


def get_winning_horses(
    win_percent, loss_percent, daily_data, hourly_data, start_date, horses
):
    winning_horses = []
    for horse in horses:
        if horse not in hourly_data:
            continue
        if start_date not in daily_data[horse]:
            continue
        if (
            daily_data[horse][start_date]["return"] > win_percent
            and daily_data[horse][start_date]["drawdown"] < loss_percent
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


def calculate_return(data, hourly_data, start_date, horses):
    for horse in horses:
        if start_date not in data[horse]:
            continue
        if horse not in hourly_data:
            continue
        initial_price = hourly_data[horse][start_date]["10:30:00"]["open"]
        close = hourly_data[horse][start_date]["16:00:00"]["close"]
        current_return = ((close - initial_price) / initial_price) * 100
        data[horse][start_date]["return"] = round(current_return, 2)


def calculate_first_hour(date, hourly_data, horses):
    for horse in horses:
        if horse not in hourly_data:
            continue
        if date not in hourly_data[horse]:
            continue
        open = hourly_data[horse][date]["10:00:00"]["open"]
        close = hourly_data[horse][date]["10:00:00"]["close"]
        first_hour_return = ((close - open) / open) * 100
        hourly_data[horse][date]["first_hour_return"] = round(first_hour_return, 2)


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
            if (
                current_open > previous_close * 1.01
                and current_open < previous_close * 1.04
            ):
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

        # ask for candle size
        candle_size = input("Please enter the candle size (D, H): ")
        if not candle_size:
            candle_size = "D"

        fetch_data(start_timestamp, end_timestamp, candle_size)
        print("Done!")

    elif user_input == "2":
        # check if data directory has at least one file
        if not os.listdir(DATA_DIR + "/" + "daily"):
            print("No data found! Please fetch data first")
        # Get win percent and loss percent
        win_percent = input("Please enter the win percent: (5) ")
        if not win_percent:
            win_percent = 5
        else:
            win_percent = int(win_percent)
        loss_percent = input("Please enter the loss percent: (2) ")
        if not loss_percent:
            loss_percent = 2
        else:
            loss_percent = int(loss_percent)
        threshold = input("Please enter the first hour threshold: (2) ")
        if not threshold:
            threshold = 2
        else:
            threshold = int(threshold)

        # Ask for verbosity level
        verbose = input("Display daily results? (y/n): (n) ")
        VERBOSE = verbose == "y"

        # Ask for interactive mode
        interactive = input("Interactive mode? (y/n): (n) ")
        INTERACTIVE = interactive == "y"

        backtest(win_percent, loss_percent, threshold)

    elif user_input == "3":
        print("Goodbye!")
        break

# Current analysis:

# if there are stocks up by 1% in premarket, there's a 33% chance that one of them will go up 5% on the day, without going down by 2%

# TODO:
"""
1. Of the pre-market stocks, which ones go up by 1% in the first hour?
    Needs:
        - algo to find horses that go up 1% in the first hour
"""
