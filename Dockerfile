FROM python:3
RUN pip install poetry

WORKDIR /code
COPY poetry.lock pyproject.toml bot/ /code/

RUN apt-get update -qq && apt-get install ffmpeg -y

RUN poetry config virtualenvs.create false \
    && poetry install

COPY . /code

EXPOSE 8080/tcp

CMD [ "python", "bot.py" ]