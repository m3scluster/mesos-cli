import json
import sys
import termios
import threading
import unittest
from queue import Queue
from unittest.mock import Mock, patch

from avmesos import recordio
from avmesos.cli.mesos import TaskIO
from avmesos.cli.plugins.task.main import Task


class TaskExecTest(unittest.TestCase):
    def setUp(self):
        self.config = Mock()
        self.config.agent_ssl.return_value = True
        self.config.agent_ssl_verify.return_value = True
        self.auth = object()
        self.config.authentication_header.return_value = self.auth

    @patch("avmesos.cli.mesos.get_container_id")
    @patch("avmesos.cli.mesos.get_agent_address")
    @patch("avmesos.cli.mesos.get_tasks")
    def test_task_io_resolves_docker_task_container(
            self, get_tasks, get_agent_address, get_container_id):
        get_tasks.return_value = [{
            "id": "synthetic-task-1",
            "state": "TASK_RUNNING",
            "slave_id": "synthetic-agent-1",
            "container": {"type": "DOCKER"},
            "statuses": [{
                "container_status": {
                    "container_id": {"value": "synthetic-container-1"}
                }
            }]
        }]
        get_agent_address.return_value = "agent.example.test:5051"
        get_container_id.return_value = {"value": "synthetic-container-1"}

        task_io = TaskIO(
            "master.example.test:5050",
            self.config,
            "synthetic-task-1")

        get_tasks.assert_called_once_with(
            "master.example.test:5050",
            self.config,
            query={"task_id": "synthetic-task-1"})
        get_agent_address.assert_called_once_with(
            "synthetic-agent-1",
            "master.example.test:5050",
            self.config)
        get_container_id.assert_called_once_with(get_tasks.return_value[0])
        self.assertEqual(
            task_io.agent_url,
            "https://agent.example.test:5051/api/v1")
        self.assertEqual(
            task_io.container_id,
            {"value": "synthetic-container-1"})

    @patch("avmesos.cli.mesos.mesos_http.Resource")
    @patch("avmesos.cli.mesos.get_container_id")
    @patch("avmesos.cli.mesos.get_agent_address")
    @patch("avmesos.cli.mesos.get_tasks")
    def test_launch_session_posts_command_to_docker_task_container(
            self,
            get_tasks,
            get_agent_address,
            get_container_id,
            resource_class):
        get_tasks.return_value = [{
            "id": "synthetic-task-1",
            "state": "TASK_RUNNING",
            "slave_id": "synthetic-agent-1",
            "container": {"type": "DOCKER"},
            "statuses": [{
                "container_status": {
                    "container_id": {"value": "synthetic-container-1"}
                }
            }]
        }]
        get_agent_address.return_value = "agent.example.test:5051"
        get_container_id.return_value = {"value": "synthetic-container-1"}
        response = resource_class.return_value.request.return_value
        response.iter_content.return_value = []

        task_io = TaskIO(
            "master.example.test:5050",
            self.config,
            "synthetic-task-1")
        task_io.container_id = {
            "parent": {"value": "synthetic-container-1"},
            "value": "synthetic-session-1"
        }
        task_io.cmd = "/bin/sh"
        task_io.args = ["-c", "printf synthetic-output"]
        task_io.tty = False

        task_io._launch_nested_container_session()

        resource_class.assert_called_once_with(
            "https://agent.example.test:5051/api/v1")
        args, kwargs = resource_class.return_value.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(json.loads(kwargs["data"]), {
            "type": "LAUNCH_NESTED_CONTAINER_SESSION",
            "launch_nested_container_session": {
                "container_id": {
                    "parent": {"value": "synthetic-container-1"},
                    "value": "synthetic-session-1"
                },
                "command": {
                    "value": "/bin/sh",
                    "arguments": [
                        "/bin/sh", "-c", "printf synthetic-output"],
                    "shell": False
                }
            }
        })
        self.assertEqual(kwargs["auth"], self.auth)
        self.assertIsNone(kwargs["timeout"])
        self.assertFalse(kwargs["retry"])
        self.assertTrue(kwargs["verify"])
        self.assertEqual(kwargs["additional_headers"], {
            "Content-Type": "application/json",
            "Accept": "application/recordio",
            "Message-Accept": "application/json"
        })

    @patch("avmesos.cli.mesos.mesos_http.Resource")
    def test_wait_returns_docker_session_exit_code(self, resource_class):
        task_io = TaskIO.__new__(TaskIO)
        task_io.agent_url = "https://agent.example.test:5051/api/v1"
        task_io.container_id = {
            "parent": {"value": "synthetic-container-1"},
            "value": "synthetic-session-1"
        }
        task_io.config = self.config
        resource_class.return_value.request.return_value.json.return_value = {
            "wait_container": {"exit_status": 7 << 8}
        }

        status = task_io._wait()

        self.assertEqual(status, 7)
        resource_class.assert_called_once_with(task_io.agent_url)
        args, kwargs = resource_class.return_value.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(json.loads(kwargs["data"]), {
            "type": "WAIT_CONTAINER",
            "wait_container": {"container_id": task_io.container_id}
        })
        self.assertEqual(kwargs["auth"], self.auth)
        self.assertIsNone(kwargs["timeout"])
        self.assertFalse(kwargs["retry"])
        self.assertTrue(kwargs["verify"])

    def test_command_dispatches_interactive_shell_by_task_id(self):
        plugin = Task(Mock(), self.config)
        plugin.exec = Mock()

        plugin.main([
            "exec", "-i", "-t", "synthetic-task-1", "/bin/sh"
        ])

        plugin.exec.assert_called_once_with({
            "--help": False,
            "--interactive": True,
            "--tty": True,
            "--version": False,
            "<args>": [],
            "<command>": "/bin/sh",
            "<task-id>": "synthetic-task-1"
        })

    @patch("avmesos.cli.mesos.signal.signal")
    @patch("avmesos.cli.mesos.termios.tcsetattr")
    @patch("avmesos.cli.mesos.termios.tcgetattr")
    @patch("avmesos.cli.mesos.tty.setraw")
    def test_interactive_tty_flushes_queued_terminal_input(
            self, setraw, tcgetattr, tcsetattr, signal_handler):
        task_io = TaskIO.__new__(TaskIO)
        task_io.tty = True
        task_io.interactive = True
        task_io.exception = None
        task_io.supports_exit_sequence = False
        task_io.exit_event = Mock()
        task_io.input_queue = Queue()
        task_io.input_ready_marker = object()
        task_io._window_resize = Mock()
        task_io._start_threads = Mock()

        stdin = Mock()
        stdin.isatty.return_value = True
        stdin.fileno.return_value = 42
        tcgetattr.return_value = ["synthetic-terminal-state"]

        with patch.object(sys, "stdin", stdin):
            task_io._run()

        setraw.assert_called_once_with(42, when=termios.TCSAFLUSH)
        tcsetattr.assert_called_once_with(
            42, termios.TCSAFLUSH, tcgetattr.return_value)
        signal_handler.assert_called_once()

    @patch("avmesos.cli.mesos.mesos_http.Resource")
    def test_interactive_input_attaches_to_docker_session(
            self, resource_class):
        task_io = TaskIO.__new__(TaskIO)
        task_io.agent_url = "https://agent.example.test:5051/api/v1"
        task_io.container_id = {
            "parent": {"value": "synthetic-container-1"},
            "value": "synthetic-session-1"
        }
        task_io.config = self.config
        task_io.tty = True
        task_io.encoder = recordio.Encoder(
            lambda value: bytes(json.dumps(value), "UTF-8"))
        task_io.input_queue = Queue()
        task_io.input_ready_marker = object()
        task_io.input_queue.put(b"synthetic-resize")
        task_io.input_queue.put(task_io.input_ready_marker)
        task_io.input_queue.put(b"synthetic-input")
        task_io.input_queue.put(None)
        task_io.attach_input_event = threading.Event()
        task_io.attach_input_event.set()
        task_io.print_output_event = threading.Event()
        task_io.exit_sequence_detected = False

        handshake_resource = Mock()
        stream_resource = Mock()
        resource_class.side_effect = [
            handshake_resource,
            stream_resource
        ]

        handshake_resource.request.side_effect = (
            lambda *args, **kwargs: list(kwargs["data"]))

        def consume_stream(*args, **kwargs):
            self.assertFalse(task_io.print_output_event.is_set())
            stream = kwargs["data"]
            next(stream)
            self.assertFalse(task_io.print_output_event.is_set())
            self.assertEqual(next(stream), b"synthetic-resize")
            self.assertFalse(task_io.print_output_event.is_set())
            self.assertEqual(next(stream), b"synthetic-input")
            self.assertTrue(task_io.print_output_event.is_set())
            with self.assertRaises(StopIteration):
                next(stream)

        stream_resource.request.side_effect = consume_stream

        task_io._attach_container_input()

        self.assertEqual(resource_class.call_count, 2)
        resource_class.assert_any_call(task_io.agent_url)
        handshake_args, handshake_kwargs = (
            handshake_resource.request.call_args)
        stream_args, stream_kwargs = stream_resource.request.call_args
        self.assertEqual(handshake_args[0], "POST")
        self.assertEqual(stream_args[0], "POST")
        self.assertEqual(handshake_kwargs["auth"], self.auth)
        self.assertEqual(stream_kwargs["auth"], self.auth)
        self.assertFalse(handshake_kwargs["retry"])
        self.assertFalse(stream_kwargs["retry"])
        self.assertIsNone(stream_kwargs["timeout"])
        expected_headers = {
            "Content-Type": "application/recordio",
            "Message-Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "close",
            "Transfer-Encoding": "chunked"
        }
        self.assertEqual(
            handshake_kwargs["additional_headers"], expected_headers)
        self.assertEqual(
            stream_kwargs["additional_headers"], expected_headers)
        self.assertTrue(task_io.print_output_event.is_set())

    @patch("avmesos.cli.mesos.mesos_http.Resource")
    def test_attach_output_uses_agent_operator_api(self, resource_class):
        task_io = TaskIO.__new__(TaskIO)
        task_io.agent_url = "https://agent.example.test:5051/api/v1"
        task_io.container_id = {"value": "synthetic-container-1"}
        task_io.config = self.config
        task_io.decoder = recordio.Decoder(
            lambda value: json.loads(value.decode("UTF-8")))
        task_io.output_queue = Queue()
        task_io.attach_input_event = threading.Event()
        task_io.print_output_event = threading.Event()
        task_io.exit_event = threading.Event()
        task_io.interactive = False
        response = resource_class.return_value.request.return_value
        response.iter_content.return_value = []

        task_io._attach_container_output()

        resource_class.assert_called_once_with(task_io.agent_url)
        args, kwargs = resource_class.return_value.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(json.loads(kwargs["data"]), {
            "type": "ATTACH_CONTAINER_OUTPUT",
            "attach_container_output": {
                "container_id": task_io.container_id
            }
        })
        self.assertEqual(kwargs["auth"], self.auth)
        self.assertTrue(task_io.attach_input_event.is_set())
        self.assertTrue(task_io.exit_event.is_set())


if __name__ == "__main__":
    unittest.main()
