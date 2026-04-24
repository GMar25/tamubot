BOT_NAME = 'tamu_scraper'

SPIDER_MODULES = ['tamubot.scraper.spiders']
NEWSPIDER_MODULE = 'tamubot.scraper.spiders'

# User-Agent as requested
USER_AGENT = 'TAMU-Student-Project-Research'

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# 1.5 second download delay
DOWNLOAD_DELAY = 1.5

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
   'tamubot.scraper.pipelines.SyllabusPipeline': 1,
   'tamubot.scraper.pipelines.ManifestPipeline': 2,
   'tamubot.scraper.pipelines.ProgressPipeline': 300,
}

FILES_STORE = 'tamu_data/raw/syllabi'


# Request Fingerprinter implementation (standard in newer Scrapy)
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
