"""Serve the real app with deterministic providers for browser verification."""
import os
from pathlib import Path

import httpx
import uvicorn

from app.main import create_app
from app.models import Record
from app.sources import conference_records


class FixtureProvider:
    def fetch(self, source, query):
        if source == 'arxiv':
            raise httpx.ReadTimeout('Synthetic outage for browser test')
        if source == 'mldeadlines':
            return conference_records((Path(__file__).parent/'fixtures/conferences.html').read_text())
        return [Record(kind='paper', source=source, external_id=str(i),
                       title=f'Graph research fixture {i:02}', year=2026,
                       abstract='Synthetic browser test metadata.', authors=['García']) for i in range(13)]

    def close(self):
        pass


if __name__ == '__main__':
    uvicorn.run(create_app(provider=FixtureProvider()), host='127.0.0.1', port=int(os.environ.get('EUREKA_TEST_PORT', '8765')))
