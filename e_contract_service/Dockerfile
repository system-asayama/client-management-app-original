FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY e_contract_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY e_contract_service /app/e_contract_service

EXPOSE 5001

CMD ["python", "-m", "e_contract_service.app"]
