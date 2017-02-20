from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from praw.exceptions import APIException
from collections import namedtuple
from selenium import webdriver
from io import BytesIO
from PIL import Image
import requests
import praw
import json
import time

TARGET_SUBREDDIT = 'test'
DATABASE = 'database.txt'


Picture = namedtuple('Picture', ['width', 'height', 'url'])


def original_size(target):
    response = requests.get(target, headers={'User-Agent': 'Chrome/56'})
    image = Image.open(BytesIO(response.content))
    return image.size


def get_bigger(smaller):
    bigger = []
    driver = webdriver.Chrome()
    driver.get('http://www.google.com/searchbyimage?image_url={}'.format(smaller.url))
    try:
        WebDriverWait(driver, timeout=10).until(expected_conditions.presence_of_element_located((By.CLASS_NAME, '_v6')))
    except TimeoutException:
        raise TimeoutException('Timed out while locating size links.')

    size_links = driver.find_element_by_class_name('_v6')
    try:
        all_sizes = size_links.find_element_by_xpath('span[@class="gl"]')
    except NoSuchElementException:
        return bigger

    all_sizes.click()
    try:
        WebDriverWait(driver, timeout=10).until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'rg_meta')))
    except TimeoutException:
        raise TimeoutException('Timed out while locating image json.')

    results = driver.find_elements_by_class_name('rg_meta')
    prev_w = 0
    prev_h = 0
    count = 0
    for result in results:
        data = json.loads(result.get_attribute("innerHTML"))
        if data['ow'] > smaller.width and data['oh'] > smaller.height and data['ow'] != prev_w and data['oh'] != prev_h:
            prev_w = data['ow']
            prev_h = data['oh']
            bigger.append(Picture(data['ow'], data['oh'], data['ou']))
            count += 1
        else:
            break
        if count == 5:
            break

    driver.quit()
    return bigger


def links(bigger, smaller):
    if bigger:
        if len(bigger) > 1:
            return 'I found some bigger than the original size! ({}x{})\n\n{}'.format(smaller.width, smaller.height, make_links(bigger))
        else:
            return 'I found one bigger than the original size! ({}x{})\n\n{}'.format(smaller.width, smaller.height, make_links(bigger))
    else:
        return "I'm sorry, I couldn't find anything bigger."


def make_links(pictures):
    if len(pictures) > 1:
        return '\n\n'.join('[{}x{}]({})'.format(p.width, p.height, p.url) for p in pictures)
    else:
        return '[{}x{}]({})'.format(pictures[0].width, pictures[0].height, pictures[0].url)


def message(comment):
    if comment.is_root:
        url = comment.submission.url
        try:
            w, h = original_size(url)
        except IOError:
            return ('Sorry, I couldn\'t complete the search.\n'
                    '**Note:** I only work on submissions that link to a direct image.')

        smaller = Picture(w, h, url)
        bigger = get_bigger(smaller)
        return links(bigger, smaller)
    else:
        return 'Sorry, I can only search on submissions, not other comments.'


def save_stamp(utc):
    with open(DATABASE, 'w') as db:
        db.write(str(utc))


def replied_to(utc):
    with open(DATABASE) as db:
        return utc < float(db.readline())


def wait_time(error_message):
    for s in error_message.split():
        if s.isdigit():
            print('waiting for {} minute(s)'.format(s))
            return int(s) * 60 + 10


def main():
    with open('secrets.json') as f:
        auth = json.load(f)

    reddit = praw.Reddit(user_agent=auth['user_agent'],
                         client_id=auth['client_id'],
                         client_secret=auth['client_secret'],
                         username=auth['username'],
                         password=auth['password'])

    subreddit = reddit.subreddit(TARGET_SUBREDDIT)
    comments = subreddit.stream.comments()
    while True:
        for comment in comments:
            if 'BiggerPlease!' in comment.body and not replied_to(comment.created_utc):
                success = False
                while not success:
                    try:
                        comment.reply(message(comment))
                        success = True
                    except APIException as e:
                        time.sleep(wait_time(e.message))

                save_stamp(comment.created_utc)


if __name__ == '__main__':
    main()
