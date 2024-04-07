import ast
import requests
import flask
from flask import request
import os
import json
import boto3
from bot import ObjectDetectionBot
from collections import Counter
from loguru import logger
from botocore.exceptions import ClientError
import signal

app = flask.Flask(__name__)

TELEGRAM_APP_URL = 'https://orb-k8s-proj.devops-int-college.com:8443'
TABLE_NAME = os.environ['TABLE_NAME']

WEBHOOK_SSL_CERT = './cerrificate/YOURPUBLIC.pem'
WEBHOOK_SSL_PRIV = './cerrificate/YOURPRIVATE.key'

secret_name = "awspro/bot/token"
region_name = "us-west-2"

session = boto3.session.Session()
client = session.client(
    service_name='secretsmanager',
    region_name=region_name,
)

try:
    get_secret_value_response = client.get_secret_value(
        SecretId=secret_name
    )
except ClientError as e:
    if e.response['Error']['Code'] == 'ResourceNotFoundException':
        print("The requested secret " + secret_name + " was not found")
    elif e.response['Error']['Code'] == 'InvalidRequestException':
        print("The request was invalid due to:", e)
    elif e.response['Error']['Code'] == 'InvalidParameterException':
        print("The request had invalid params:", e)
    elif e.response['Error']['Code'] == 'DecryptionFailure':
        print("The requested secret can't be decrypted using the provided KMS key:", e)
    elif e.response['Error']['Code'] == 'InternalServiceError':
        print("An error occurred on service side:", e)
else:
    if 'SecretString' in get_secret_value_response:
        secret = get_secret_value_response['SecretString']
    else:
        secret = get_secret_value_response['SecretBinary']


"""load TELEGRAM_TOKEN value from Secret Manager"""
TELEGRAM_TOKEN = json.loads(secret)['TELEGRAM_TOKEN']

@app.route('/', methods=['GET'])
def index():
    return 'Ok'


@app.route(f'/{TELEGRAM_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'


@app.route(f'/results/', methods=['GET'])
def results():
    """use the prediction_id to retrieve results from DynamoDB and send to the end-user"""
    prediction_id = request.args.get('predictionId')
    client = boto3.client('dynamodb', region_name='us-west-2')
    respone = client.get_item(Key={
        'prediction_id': {
            'S': prediction_id
        }
    },
        TableName=TABLE_NAME
    )

    document = respone['Item']
    data = document['labels']
    data_list = ast.literal_eval(data['S'])
    object_labels = []
    for x in data_list:
        object_labels.append(x['class'])
    object_counts = Counter(object_labels)
    ans = ','.join([f'\n{obj}, {count}' for obj, count in object_counts.items()])
    sums = sum(object_counts.values())
    text_results = f'There {sums} Object in Picture : {ans}\n Thank you!'
    logger.info(f'There {sums} Object in Picture : {ans}\n Thank you!')
    chat_id = bot.chat_id
    bot.send_text(chat_id, text_results)
    return 'Ok'

@app.route(f'/health', methods=['GET'])
def liveness():
    return 'Ok'

@app.route(f'/ready', methods=['GET'])
def readiness():
    return 'Ok'

def sigterm_handler(signum, frame):
    print("Received SIGTERM, shutting down...")
    message = "Received SIGTERM, shutting down..."
    chat_id = bot.chat_id
    logger.info('shutting down...')
    bot.send_message(chat_id=chat_id, text=message)
    exit(0)
signal.signal(signal.SIGTERM, sigterm_handler)


if __name__ == "__main__":
    bot = ObjectDetectionBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL, WEBHOOK_SSL_CERT)
    app.run(host='0.0.0.0', port=8443, debug=True)


