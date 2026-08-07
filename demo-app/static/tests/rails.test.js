import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchRails} from '../rails.js';

test('rails are loaded from the local rails API', async () => {
  const expected = [
    {title: 'Trending', movie_ids: ['afterlight']},
    {title: 'Watchlist', movie_ids: []},
    {title: 'Science Fiction', movie_ids: ['static-sea']},
    {title: 'Mystery', movie_ids: ['velvet-signal']},
  ];
  const requests = [];
  const fetcher = async url => {
    requests.push(url);
    return {ok: true, json: async () => expected};
  };

  assert.deepEqual(await fetchRails(fetcher), expected);
  assert.deepEqual(requests, ['/api/rails']);
});

test('invalid rails API responses are rejected', async () => {
  const fetcher = async () => ({
    ok: true,
    json: async () => [{title: 'Trending'}],
  });

  await assert.rejects(fetchRails(fetcher), /invalid payload/);
});
