import mock
from tests import BaseTestCase

from redash.models import db
from redash.utils import gen_query_hash, json_dumps

class TestQueryResultsCacheHeaders(BaseTestCase):
    def test_uses_cache_headers_for_specific_result(self):
        query_result = self.factory.create_query_result()
        query = self.factory.create_query(latest_query_data=query_result)

        rv = self.make_request('get', '/api/queries/{}/results/{}.json'.format(query.id, query_result.id))
        self.assertIn('Cache-Control', rv.headers)

    def test_doesnt_use_cache_headers_for_non_specific_result(self):
        query_result = self.factory.create_query_result()
        query = self.factory.create_query(latest_query_data=query_result)

        rv = self.make_request('get', '/api/queries/{}/results.json'.format(query.id))
        self.assertNotIn('Cache-Control', rv.headers)

    def test_returns_404_if_no_cached_result_found(self):
        query = self.factory.create_query(latest_query_data=None)

        rv = self.make_request('get', '/api/queries/{}/results.json'.format(query.id))
        self.assertEqual(404, rv.status_code)


class TestQueryResultListAPI(BaseTestCase):
    def test_get_existing_result(self):
        query_result = self.factory.create_query_result()
        query = self.factory.create_query()

        rv = self.make_request('post', '/api/query_results',
                               data={'data_source_id': self.factory.data_source.id,
                                     'query': query.query_text})
        self.assertEquals(rv.status_code, 200)
        self.assertEquals(query_result.id, rv.json['query_result']['id'])

    def test_execute_new_query(self):
        query = self.factory.create_query()

        rv = self.make_request('post', '/api/query_results',
                               data={'data_source_id': self.factory.data_source.id,
                                     'query': query.query_text,
                                     'max_age': 0})

        self.assertEquals(rv.status_code, 200)
        self.assertNotIn('query_result', rv.json)
        self.assertIn('job', rv.json)

    def test_queue_length(self):
        query = self.factory.create_query()
        tasks = []
        def fake_all(*a, **kw):
            return tasks
        def enqueue_query(query, *a, **kw):
            from redash.tasks.queries import enqueue_query
            job = enqueue_query(query, *a, **kw)
            tasks.append(dict(
                state='waiting_in_queue',
                task_name='test task',
                worker=None,
                worker_pid=None,
                start_time=None,
                task_id=job.id,
                queue='queries',
            ))
            return job
        patch_all = mock.patch('redash.handlers.query_results.get_waiting_in_queue', fake_all)
        patch_parse_tasks = mock.patch('redash.handlers.query_results.parse_tasks', lambda *_: [])
        patch_enqueue_query = mock.patch('redash.handlers.query_results.enqueue_query',
                                         enqueue_query)
        db.session.commit()
        with patch_all, patch_enqueue_query, patch_parse_tasks:
            job0 = self.make_request('post', '/api/query_results',
                                     data={'data_source_id': self.factory.data_source.id,
                                           'query': query.query_text,
                                           'max_age': 0})
            rv0 = self.make_request('get', '/api/queue_status/{}?data_source={}'.format(
                job0.json['job']['id'], self.factory.data_source.id))
            job1 = self.make_request('post', '/api/query_results',
                                     data={'data_source_id': self.factory.data_source.id,
                                           'query': query.query_text,
                                           'max_age': 0})
            rv1 = self.make_request('get', '/api/queue_status/{}?data_source={}'.format(
                job1.json['job']['id'], self.factory.data_source.id))
            job2 = self.make_request('post', '/api/query_results',
                                     data={'data_source_id': self.factory.data_source.id,
                                           'query': query.query_text,
                                           'max_age': 0})
            rv2 = self.make_request('get', '/api/queue_status/{}?data_source={}'.format(
                job2.json['job']['id'], self.factory.data_source.id))

        self.assertEquals(rv0.json['num_tasks'], 1)
        self.assertEquals(rv1.json['num_tasks'], 2)
        self.assertEquals(rv2.json['num_tasks'], 3)


    def test_execute_query_without_access(self):
        group = self.factory.create_group()
        db.session.commit()
        user = self.factory.create_user(group_ids=[group.id])
        query = self.factory.create_query()

        rv = self.make_request('post', '/api/query_results',
                               data={'data_source_id': self.factory.data_source.id,
                                     'query': query.query_text,
                                     'max_age': 0},
                               user=user)

        self.assertEquals(rv.status_code, 403)
        self.assertIn('job', rv.json)

    def test_execute_query_with_params(self):
        query = "SELECT {{param}}"

        rv = self.make_request('post', '/api/query_results',
                               data={'data_source_id': self.factory.data_source.id,
                                     'query': query,
                                     'max_age': 0})

        self.assertEquals(rv.status_code, 400)
        self.assertIn('job', rv.json)

        rv = self.make_request('post', '/api/query_results',
                               data={'data_source_id': self.factory.data_source.id,
                                     'query': query,
                                     'parameters': {'param': 1},
                                     'max_age': 0})

        self.assertEquals(rv.status_code, 200)
        self.assertIn('job', rv.json)

        rv = self.make_request('post', '/api/query_results?p_param=1',
                               data={'data_source_id': self.factory.data_source.id,
                                     'query': query,
                                     'max_age': 0})

        self.assertEquals(rv.status_code, 200)
        self.assertIn('job', rv.json)

    def test_execute_on_paused_data_source(self):
        self.factory.data_source.pause()

        rv = self.make_request('post', '/api/query_results',
                               data={'data_source_id': self.factory.data_source.id,
                                     'query': 'SELECT 1',
                                     'max_age': 0})

        self.assertEquals(rv.status_code, 400)
        self.assertNotIn('query_result', rv.json)
        self.assertIn('job', rv.json)


class TestQueryResultAPI(BaseTestCase):
    def test_has_no_access_to_data_source(self):
        ds = self.factory.create_data_source(group=self.factory.create_group())
        query_result = self.factory.create_query_result(data_source=ds)

        rv = self.make_request('get', '/api/query_results/{}'.format(query_result.id))
        self.assertEquals(rv.status_code, 403)

    def test_has_view_only_access_to_data_source(self):
        ds = self.factory.create_data_source(group=self.factory.org.default_group, view_only=True)
        query_result = self.factory.create_query_result(data_source=ds)

        rv = self.make_request('get', '/api/query_results/{}'.format(query_result.id))
        self.assertEquals(rv.status_code, 200)

    def test_has_full_access_to_data_source(self):
        ds = self.factory.create_data_source(group=self.factory.org.default_group, view_only=False)
        query_result = self.factory.create_query_result(data_source=ds)

        rv = self.make_request('get', '/api/query_results/{}'.format(query_result.id))
        self.assertEquals(rv.status_code, 200)

    def test_execute_new_query(self):
        query = self.factory.create_query()

        rv = self.make_request('post', '/api/queries/{}/results'.format(query.id), data={'parameters': {}})

        self.assertEquals(rv.status_code, 200)
        self.assertIn('job', rv.json)

    def test_prevents_execution_of_unsafe_queries_on_view_only_data_sources(self):
        ds = self.factory.create_data_source(group=self.factory.org.default_group, view_only=True)
        query = self.factory.create_query(data_source=ds, options={"parameters": [{"name": "foo", "type": "text"}]})

        rv = self.make_request('post', '/api/queries/{}/results'.format(query.id), data={"parameters": {}})
        self.assertEquals(rv.status_code, 403)

    def test_allows_execution_of_safe_queries_on_view_only_data_sources(self):
        ds = self.factory.create_data_source(group=self.factory.org.default_group, view_only=True)
        query = self.factory.create_query(data_source=ds, options={"parameters": [{"name": "foo", "type": "number"}]})

        rv = self.make_request('post', '/api/queries/{}/results'.format(query.id), data={"parameters": {}})
        self.assertEquals(rv.status_code, 200)

    def test_access_with_query_api_key(self):
        ds = self.factory.create_data_source(group=self.factory.org.default_group, view_only=False)
        query = self.factory.create_query()
        query_result = self.factory.create_query_result(data_source=ds, query_text=query.query_text)

        rv = self.make_request('get', '/api/queries/{}/results/{}.json?api_key={}'.format(query.id, query_result.id, query.api_key), user=False)
        self.assertEquals(rv.status_code, 200)

    def test_access_with_query_api_key_without_query_result_id(self):
        ds = self.factory.create_data_source(group=self.factory.org.default_group, view_only=False)
        query = self.factory.create_query()
        query_result = self.factory.create_query_result(data_source=ds, query_text=query.query_text, query_hash=query.query_hash)
        query.latest_query_data = query_result

        rv = self.make_request('get', '/api/queries/{}/results.json?api_key={}'.format(query.id, query.api_key), user=False)
        self.assertEquals(rv.status_code, 200)

    def test_query_api_key_and_different_query_result(self):
        ds = self.factory.create_data_source(group=self.factory.org.default_group, view_only=False)
        query = self.factory.create_query(query_text="SELECT 8")
        query_result2 = self.factory.create_query_result(data_source=ds, query_hash='something-different')

        rv = self.make_request('get', '/api/queries/{}/results/{}.json?api_key={}'.format(query.id, query_result2.id, query.api_key), user=False)
        self.assertEquals(rv.status_code, 404)

    def test_signed_in_user_and_different_query_result(self):
        ds2 = self.factory.create_data_source(group=self.factory.org.admin_group, view_only=False)
        query = self.factory.create_query(query_text="SELECT 8")
        query_result2 = self.factory.create_query_result(data_source=ds2, query_hash='something-different')

        rv = self.make_request('get', '/api/queries/{}/results/{}.json'.format(query.id, query_result2.id))
        self.assertEquals(rv.status_code, 403)


class TestQueryResultDropdownResource(BaseTestCase):
    def test_checks_for_access_to_the_query(self):
        ds2 = self.factory.create_data_source(group=self.factory.org.admin_group, view_only=False)
        query = self.factory.create_query(data_source=ds2)

        rv = self.make_request('get', '/api/queries/{}/dropdown'.format(query.id))

        self.assertEquals(rv.status_code, 403)

class TestQueryDropdownsResource(BaseTestCase):
    def test_prevents_access_if_query_isnt_associated_with_parent(self):
        query = self.factory.create_query()
        unrelated_dropdown_query = self.factory.create_query()

        rv = self.make_request('get', '/api/queries/{}/dropdowns/{}'.format(query.id, unrelated_dropdown_query.id))

        self.assertEquals(rv.status_code, 403)

    def test_allows_access_if_user_has_access_to_parent_query(self):
        query_result = self.factory.create_query_result()
        data = {
            'rows': [],
            'columns': [{'name': 'whatever'}]
        }
        query_result = self.factory.create_query_result(data=json_dumps(data))
        dropdown_query = self.factory.create_query(latest_query_data=query_result)

        options = {
                'parameters': [{
                'type': 'query',
                'queryId': dropdown_query.id
            }]
        }
        query = self.factory.create_query(options=options)

        rv = self.make_request('get', '/api/queries/{}/dropdowns/{}'.format(query.id, dropdown_query.id))

        self.assertEquals(rv.status_code, 200)

    def test_prevents_access_if_user_doesnt_have_access_to_parent_query(self):
        related_dropdown_query = self.factory.create_query()
        unrelated_dropdown_query = self.factory.create_query()
        options = {
                'parameters': [{
                'type': 'query',
                'queryId': related_dropdown_query.id
            }]
        }
        query = self.factory.create_query(options=options)

        rv = self.make_request('get', '/api/queries/{}/dropdowns/{}'.format(query.id, unrelated_dropdown_query.id))

        self.assertEquals(rv.status_code, 403)

class TestQueryResultExcelResponse(BaseTestCase):
    def test_renders_excel_file(self):
        query = self.factory.create_query()
        query_result = self.factory.create_query_result()

        rv = self.make_request('get', '/api/queries/{}/results/{}.xlsx'.format(query.id, query_result.id), is_json=False)
        self.assertEquals(rv.status_code, 200)

    def test_renders_excel_file_when_rows_have_missing_columns(self):
        query = self.factory.create_query()
        data = {
            'rows': [
                {'test': 1},
                {'test': 2, 'test2': 3},
            ],
            'columns': [
                {'name': 'test'},
                {'name': 'test2'},
            ],
        }
        query_result = self.factory.create_query_result(data=json_dumps(data))

        rv = self.make_request('get', '/api/queries/{}/results/{}.xlsx'.format(query.id, query_result.id), is_json=False)
        self.assertEquals(rv.status_code, 200)

