import telebot
from loguru import logger
import os
import time
import boto3
import json
from telebot.types import InputFile


class Bot:

    def __init__(self, token, telegram_chat_url, ssl_pub):
        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        self.telegram_bot_client = telebot.TeleBot(token)

        # remove any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)

        # set the webhook URL
        self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', certificate=open(ssl_pub, 'r'),
                                             timeout=60)

        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        """
        Downloads the photos that sent to the Bot to `photos` directory (should be existed)
        :return:
        """
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)

        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")

        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )

    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


class ObjectDetectionBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')
        self.chat_id = msg['chat']['id']

        if self.is_current_msg_photo(msg):
            photo_path = self.download_user_photo(msg)
            logger.info(photo_path)
            img_name = self.download_user_photo(msg).split('/')[1]
            """upload the photo to S3"""
            s3 = boto3.client('s3', region_name='us-west-2')
            s3.upload_file(photo_path, 'awsproj-orb', f'images/{img_name}')
            """send job to sqs"""
            sqs = boto3.client('sqs', region_name='us-west-2')
            queue_url = 'https://sqs.us-west-2.amazonaws.com/352708296901/sqs-aws-project'
            message = {'chat_id': msg['chat']['id'], 'img_name': img_name}
            response = sqs.send_message(
                QueueUrl=queue_url,
                DelaySeconds=10,
                MessageBody=json.dumps(message)
            )
            """send message to the Telegram end-user """
            self.telegram_bot_client.send_message(msg['chat']['id'], text= "Thank you, wait patiently your image is being processed ")
        elif msg['text'] == '/end':
            self.telegram_bot_client.send_message(msg['chat']['id'], text='Thank you!!! I`m here for you, come back whenever you want')
            time.sleep(2)
            self.telegram_bot_client.send_message(msg['chat']['id'],
                                                  text='How would you rate the service?\n1- Very bad\n5- Excellent')
            if msg['text'] == True:
                self.telegram_bot_client.send_message(msg['chat']['id'],
                                                      text='Thanks for the answer, passing the answer to the creators!')
        elif msg['text'] == '/help':
            self.telegram_bot_client.send_message(msg['chat']['id'],
                                                  text='I am base on Yolo5 object detection AI model. It is known for its high accuracy object detection in images and videos, I can detect 80 objects.\n Try me!\n Send me a Photo like the example below')
            self.telegram_bot_client.send_video(msg['chat']['id'], video=open('helpVideo.mp4', 'rb'),
                                                supports_streaming=True)
        elif msg['text'] == '/start':
            self.telegram_bot_client.send_message(msg['chat']['id'],
                                                  text='Hi, my name is Yolobot.\nPlease send me a photo and I will try to predict the objects in your image')
        else:
            self.telegram_bot_client.send_message(msg['chat']['id'],
                                                  text='Sorry but I dont unsderstand what that means " {} ".\n Try using these command for help: /help'.format(
                                                      msg["text"]))


