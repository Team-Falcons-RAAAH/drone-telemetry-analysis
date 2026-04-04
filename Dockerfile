FROM python:3.14

WORKDIR /program
COPY . /program

RUN pip install -r requirements.txt

EXPOSE 8000

CMD ["python", "app.py",]




