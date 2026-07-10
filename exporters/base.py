"""
Exporters are responsible for taking the data from the database and converting it into a format that can be used by other systems. 
This module provides a base class for all exporters, which can be extended to create custom exporters for different formats.
"""
from abc import ABC, abstractmethod

class BaseExporter(ABC):
    """
    Base class for all exporters. This class defines the interface that all exporters must implement.
    """

    @abstractmethod
    def export(self, data):
        """
        Export the given data to the desired format.

        :param data: The data to be exported.
        :return: The exported data in the desired format.
        """
        pass