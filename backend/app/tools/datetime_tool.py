from datetime import datetime


class DateTimeTool:
    name = "datetime"

    def run(self, input_text: str):
        now = datetime.now()

        return now.strftime("%Y-%m-%d %H:%M:%S")
