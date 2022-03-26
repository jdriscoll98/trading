from pprint import pprint
import time
import requests
import matplotlib.pyplot as plt

# read constituents.csv and return a list of tuples


def read_constituents():
    with open('constituents.csv', 'r') as f:
        lines = f.readlines()
    lines = [line.strip().split(',') for line in lines]
    return lines


def fetch_data():
    stocks = read_constituents()

    URL = "https://query1.finance.yahoo.com/v7/finance/download/{symbol}?period1=1490486400&period2=1648252800&interval=1d&events=history&includeAdjustedClose=true"

    for stock in stocks[1:]:
        symbol = stock[0]
        formattedURL = URL.format(symbol=symbol)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
        r = requests.get(formattedURL, headers=headers)
        with open("data/" + symbol + '.csv', 'w') as f:
            f.write(r.text)

        time.sleep(2)


def backtest():
    # starting from the second day
    # list all of the stocks that opened 1% or more above the previous close
    # for each stock, calculate the daily return

    # read data
    stocks = read_constituents()
    # read data from stocks
    data = {}
    for stock in stocks[1:]:
        symbol = stock[0]
        data[symbol] = {}
        with open("data/" + symbol + '.csv', 'r') as f:
            lines = f.readlines()
        stock_data = [line.strip().split(',') for line in lines]
        for line in stock_data[1:]:
            if ('null' in line):
                continue
            data[symbol][line[0]] = {
                'open': float(line[1]),
                'high': float(line[2]),
                'low': float(line[3]),
                'close': float(line[4]),
                'adj_close': float(line[5]),
                'volume': float(line[6]),
            }

    start_timestamp = 1490486400
    end_timestamp = 1648252800

    # comvert to datetime
    start_date = time.strftime('%Y-%m-%d', time.localtime(start_timestamp))
    end_date = time.strftime('%Y-%m-%d', time.localtime(end_timestamp))

    print("start date: " + start_date)
    print("end date: " + end_date)

    # for each day
    losing_days, winning_days = 0, 0
    while (start_timestamp < end_timestamp - 86400):
        horses = []
        #  add a day
        start_timestamp += 86400
        start_date = time.strftime('%Y-%m-%d', time.localtime(start_timestamp))
        # list each stock that opened 1% or more above the previous close
        for stock in stocks[1:]:
            symbol = stock[0]
            if (start_date not in data[symbol]):
                continue
            # calculate the daily return
            yesterday = start_timestamp - 86400
            yesterday_date = time.strftime(
                '%Y-%m-%d', time.localtime(yesterday))
            if (yesterday_date in data[symbol]):
                previous_close = data[symbol][yesterday_date]['close']
                current_open = data[symbol][start_date]['open']
                if (current_open > previous_close * 1.01):
                    horses.append(symbol)
        # for each horse, calclate current current days return
        for horse in horses:
            if (start_date not in data[horse]):
                continue
            current_open = data[horse][start_date]['open']
            current_close = data[horse][start_date]['close']
            current_return = (
                current_close - current_open) / current_close
            data[horse][start_date]['return'] = current_return

        # for each horse, calculate the total drawdown
        for horse in horses:
            if (start_date not in data[horse]):
                continue
            current_open = data[horse][start_date]['open']
            current_low = data[horse][start_date]['low']
            current_drawdown = (current_open - current_low) / current_open
            data[horse][start_date]['drawdown'] = current_drawdown

        winning_horses = []

        # if the horse has a return greater than 5%, and drawdown is less than 3%, add to winning horses
        for horse in horses:
            if (start_date not in data[horse]):
                continue
            if (data[horse][start_date]['return'] > 0.05 and data[horse][start_date]['drawdown'] < 0.02):
                winning_horses.append(horse)

        # print the winning horses
        print("winning horses on " + start_date + ": " + str(winning_horses))

        # print daily winning percentage
        if (len(horses) > 0):
            winning_percentage = len(winning_horses) / len(horses)
            print(start_date, ": winning percentage: " + str(winning_percentage))
        else:
            print(start_date, ": no horses")
        if (len(winning_horses) == 0 and len(horses) > 0):
            losing_days += 1
            print("no winning horses on " + start_date)
        else:
            winning_days += 1

    print("winning days: " + str(winning_days))
    print("losing days: " + str(losing_days))
    print("winning percent: " + str(winning_days / (winning_days + losing_days)))


backtest()
# fetch_data()
