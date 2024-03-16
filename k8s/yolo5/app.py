import time
from pathlib import Path
import requests
from detect import run
import yaml
from loguru import logger
import json
import os
import boto3

images_bucket = os.environ['BUCKET_NAME']
queue_name = os.environ['SQS_QUEUE_NAME']

sqs_client = boto3.client('sqs', region_name='us-west-2')

with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']


def consume():
    while True:
        response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)

        if 'Messages' in response:
            message = response['Messages'][0]['Body']
            receipt_handle = response['Messages'][0]['ReceiptHandle']

            # Use the ReceiptHandle as a prediction UUID
            prediction_id = response['Messages'][0]['MessageId']

            logger.info(f'prediction: {prediction_id}. start processing')

            # Receives a URL parameter representing the image to download from S3
            img_name = json.loads(message)['img_name']
            chat_id = json.loads(message)['chat_id']
            original_img_path = f'Image/{img_name}'

            """download img_name from S3"""
            s3 = boto3.client('s3', region_name='us-west-2')
            s3.download_file(images_bucket, f'images/{img_name}', original_img_path)
            logger.info(f'prediction: {prediction_id}/{original_img_path}. Download img completed')



            # Predicts the objects in the image
            run(
                weights='yolov5s.pt',
                data='data/coco128.yaml',
                source=original_img_path,
                project='static/data',
                name=prediction_id,
                save_txt=True
            )

            logger.info(f'prediction: {prediction_id}/{original_img_path}. done')

            # This is the path for the predicted image with labels
            # The predicted image typically includes bounding boxes drawn around the detected objects, along with class labels and possibly confidence scores.
            predicted_img_path = Path(f'static/data/{prediction_id}/{img_name}')

            """Uploads the predicted image (predicted_img_path) to S3 """
            s3.upload_file(predicted_img_path, images_bucket, f'predicted/predict_{img_name}')

            # Parse prediction labels and create a summary
            pred_summary_path = Path(f'static/data/{prediction_id}/labels/{img_name.split(".")[0]}.txt')
            if pred_summary_path.exists():
                with open(pred_summary_path) as f:
                    labels = f.read().splitlines()
                    labels = [line.split(' ') for line in labels]
                    labels = [{
                        'class': names[int(l[0])],
                        'cx': float(l[1]),
                        'cy': float(l[2]),
                        'width': float(l[3]),
                        'height': float(l[4]),
                    } for l in labels]

                logger.info(f'prediction: {prediction_id}/{original_img_path}. prediction summary:\n\n{labels}')

                prediction_summary = {
                    'prediction_id': prediction_id,
                    'original_img_path': str(original_img_path),
                    'predicted_img_path': str(predicted_img_path),
                    'labels': str(labels),
                    'time': str(time.time())
                }
                logger.info(type(prediction_summary))
                """store the prediction_summary in a DynamoDB table"""
                try:
                    client = boto3.resource('dynamodb', region_name='us-west-2' )
                    response = client.Table('db-awsproj-orb')
                    response.put_item(Item=prediction_summary)
                    logger.info('Put prediction_summary in dynamo',prediction_summary)
                except:
                    raise EOFError

            """ perform a GET request to Polybot to `/results` endpoint in app.py """

            Yolo2bot = requests.get(url=f'https://orb-k8s-proj.devops-int-college.com:8443/results/?predictionId={prediction_id}', verify=False)


            # Delete the message from the queue as the job is considered as DONE
            sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)


if __name__ == "__main__":
    consume()
