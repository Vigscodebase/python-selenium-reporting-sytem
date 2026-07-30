from datetime import datetime, timedelta
import logging

class DSRService():

    def check_eligibility(self, report_day):
        try:
            report_day = int(report_day)
        except ValueError:
            logging.error(f"Cannot convert report_day into integer; report_day={report_day}")
            return False  # Return False if the report_day is invalid

        # Get today's date
        today = datetime.today().date()
        # Get the last day of the current month
        last_day = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Eligibility checks:
        if report_day == today.day:
            return True
        # If report day is greater than today and today is the last day of the month
        elif report_day > today.day and today == last_day:
            return True
        else:
            return False

    def create_month_day_dict(self, year, long_only=False):
        months_names = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10','11','12']
        # Adjust for leap year: February will have 29 days in a leap year
        days_in_month = [31, 28 + (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

        return dict((k, v) for k, v in zip(months_names, days_in_month) if not long_only or v == 31)

if __name__ == '__main__':
    dsr = DSRService()
    print(dsr.check_eligibility(25)) 
