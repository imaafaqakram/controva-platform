try:
    with open("/var/log/asterisk/full") as log:
        print(log.readline())
except FileNotFoundError:
    print("Log file not found. Check the Asterisk log path.")