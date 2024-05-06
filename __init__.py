from urllib.parse import urlencode
from urllib.request import urlopen, Request

from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source
from calibre.ebooks.BeautifulSoup import BeautifulSoup

class Yes24(Source):

    name = "Yes24 Cover"
    description = "Downloads covers from Yes24."    
    author = "Limeade23 <https://github.com/limeade23>"
    version = (0, 0, 1)
    minimum_calibre_version = (6, 10, 0)

    YES24_ID: str = "yes24"
    SEARCH_URL: str = "https://www.yes24.com/Product/Search"
    GOODS_URL: str = "https://www.yes24.com/Product/Goods/"

    capabilities = frozenset(["cover"])
    
    def _get_product_id(self, data, timeout: int = 30):
        params = {"query": data}
        query_string = urlencode(params)
        url = f"{self.SEARCH_URL}?{query_string}"
        request = Request(url, method="GET")

        with urlopen(request, timeout=timeout) as response:
            html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            
            id_list = [li['data-goods-no'] for li in soup.find_all('li', {'data-goods-no': True})]
            return id_list[0]
        

    def download_cover(
        self,
        log,
        result_queue,
        abort,
        title=None,
        authors=None,
        identifiers={},
        timeout=30,
        get_best_cover=False,
    ):
        isbn = identifiers.get('isbn', None)

        if isbn:
            product_id = self._get_product_id(isbn)
            cover_url = f"https://image.yes24.com/goods/{product_id}/XL"
            try:
                log.info("Trying to download cover from: %s", cover_url)
                with urlopen(cover_url, timeout=timeout) as response:
                    cover = response.read()
                    result_queue.put((self, cover))
            except Exception as e:
                log.exception("Failed to download cover from: %s", cover_url)
        else:
            log.info("No cover found")