from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from praw.exceptions import APIException
from collections import namedtuple
from selenium import webdriver
from contextlib import closing
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
	response = requests.get(target, headers={'User-Agent': 'Chrome/63'})  # including user agent increases success
	image = Image.open(BytesIO(response.content))
	return image.size


def process(results, bigger, smaller):
	prev_w = 0
	prev_h = 0
	count = 0
	for result in results:
		data = json.loads(result.get_attribute("innerHTML"))
		if data['ow'] != prev_w and data['oh'] != prev_h and data['ow'] > smaller.width and data['oh'] > smaller.height and count < 5:
			prev_w = data['ow']
			prev_h = data['oh']
			bigger.append(Picture(data['ow'], data['oh'], data['ou']))
			count += 1
		else:
			break

	return bigger


def get_bigger(smaller):
	bigger = []
	with closing(webdriver.Chrome()) as driver:
		driver.get(f'http://www.google.com/searchbyimage?image_url={smaller.url}')
		try:
			WebDriverWait(driver, timeout=10).until(expected_conditions.presence_of_element_located((By.CLASS_NAME, '_v6')))
		except TimeoutException:
			raise TimeoutException('Timed out while locating size links')

		size_links = driver.find_element_by_class_name('_v6')
		try:
			all_sizes = size_links.find_element_by_xpath('span[@class="gl"]')
		except NoSuchElementException:
			return bigger

		all_sizes.click()
		try:
			WebDriverWait(driver, timeout=10).until(expected_conditions.presence_of_element_located((By.CLASS_NAME, 'rg_meta')))
		except TimeoutException:
			raise TimeoutException('Timed out while locating image json')

		results = driver.find_elements_by_class_name('rg_meta')
		bigger = process(results, bigger, smaller)

	return bigger


def links(bigger, smaller):
	if bigger:
		amount = 'some' if len(bigger) > 1 else 'one'
		return f'I found {amount} bigger than the original size! ({smaller.width}x{smaller.height})\n\n{make_links(bigger)}'
	else:
		return "I'm sorry, I couldn't find anything bigger."


def make_links(pictures):
	if len(pictures) > 1:
		return '\n\n'.join(f'[{p.width}x{p.height}]({p.url})' for p in pictures)
	else:
		return f'[{pictures[0].width}x{pictures[0].height}]({pictures[0].url})'


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
			return int(s) * 60 + 10  # 10 seconds padding to ensure timeout has passed


def main():
	with open('secrets.json') as f:
		auth = json.load(f)

	reddit = praw.Reddit(user_agent=auth['user_agent'],
	                     client_id=auth['client_id'],
	                     client_secret=auth['client_secret'],
	                     username=auth['username'],
	                     password=auth['password'])

	subreddit = reddit.subreddit(TARGET_SUBREDDIT)

	for comment in subreddit.stream.comments():
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
