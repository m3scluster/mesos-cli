import json
import unittest
from unittest.mock import Mock, patch

from avmesos.cli.exceptions import CLIException
from avmesos.cli.plugins.task.main import Task


class TaskMemoryTest(unittest.TestCase):
    def setUp(self):
        self.config = Mock()
        self.config.master.return_value = "master.example.test:5050"
        self.config.agent_ssl.return_value = True
        self.config.agent_ssl_verify.return_value = True
        self.config.agent_timeout.return_value = 7
        self.auth = object()
        self.config.authentication_header.return_value = self.auth
        self.plugin = Task(Mock(), self.config)

    @patch("avmesos.cli.plugins.task.main.mesos_http.Resource")
    @patch("avmesos.cli.plugins.task.main.get_agent_address")
    @patch("avmesos.cli.plugins.task.main.get_tasks")
    def test_update_memory_resolves_task_and_updates_owning_agent(
            self, get_tasks, get_agent_address, resource_class):
        get_tasks.return_value = [{
            "id": "synthetic-task-1",
            "state": "TASK_RUNNING",
            "slave_id": "synthetic-agent-1",
            "statuses": [{
                "container_status": {
                    "container_id": {"value": "synthetic-container-1"}
                }
            }]
        }]
        get_agent_address.return_value = "agent.example.test:5051"
        resource = resource_class.return_value

        self.plugin.update_memory({
            "<task-id>": "synthetic-task-1",
            "<memory-mib>": "256"
        })

        get_tasks.assert_called_once_with(
            "master.example.test:5050",
            self.config,
            query={"task_id": "synthetic-task-1"})
        get_agent_address.assert_called_once_with(
            "synthetic-agent-1", "master.example.test:5050", self.config)
        resource_class.assert_called_once_with(
            "https://agent.example.test:5051/api/v1")
        args, kwargs = resource.request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(json.loads(kwargs["data"]), {
            "type": "UPDATE_CONTAINER_MEMORY_LIMIT",
            "update_container_memory_limit": {
                "container_id": {"value": "synthetic-container-1"},
                "memory_limit": {"value": 256}
            }
        })
        self.assertEqual(kwargs["auth"], self.auth)
        self.assertEqual(kwargs["timeout"], 7)
        self.assertTrue(kwargs["verify"])
        self.assertEqual(kwargs["additional_headers"], {
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    @patch("avmesos.cli.plugins.task.main.get_tasks")
    def test_update_memory_rejects_non_running_task(self, get_tasks):
        get_tasks.return_value = [{
            "id": "synthetic-task-1",
            "state": "TASK_FINISHED",
            "slave_id": "synthetic-agent-1",
            "statuses": []
        }]

        with self.assertRaisesRegex(CLIException, "running task"):
            self.plugin.update_memory({
                "<task-id>": "synthetic-task-1",
                "<memory-mib>": "256"
            })

    def test_update_memory_rejects_non_positive_memory(self):
        with self.assertRaisesRegex(CLIException, "positive integer"):
            self.plugin.update_memory({
                "<task-id>": "synthetic-task-1",
                "<memory-mib>": "0"
            })

    def test_update_memory_rejects_non_numeric_memory(self):
        with self.assertRaisesRegex(CLIException, "positive integer"):
            self.plugin.update_memory({
                "<task-id>": "synthetic-task-1",
                "<memory-mib>": "many"
            })

    @patch("avmesos.cli.plugins.task.main.get_tasks")
    def test_update_memory_reports_missing_container_id(self, get_tasks):
        get_tasks.return_value = [{
            "id": "synthetic-task-1",
            "state": "TASK_RUNNING",
            "slave_id": "synthetic-agent-1",
            "statuses": [{"state": "TASK_RUNNING"}]
        }]

        with self.assertRaisesRegex(CLIException, "Could not get container ID"):
            self.plugin.update_memory({
                "<task-id>": "synthetic-task-1",
                "<memory-mib>": "256"
            })

    def test_command_dispatches_update_memory_arguments(self):
        self.plugin.update_memory = Mock()

        self.plugin.main([
            "update-memory", "synthetic-task-1", "256"
        ])

        self.plugin.update_memory.assert_called_once_with({
            "--help": False,
            "--version": False,
            "<memory-mib>": "256",
            "<task-id>": "synthetic-task-1"
        })


if __name__ == "__main__":
    unittest.main()
