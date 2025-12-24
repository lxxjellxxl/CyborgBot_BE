from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet


class BaseModelViewSet(ModelViewSet):
    ordering = ['id']

    def perform_create(self, serializer):
        user = self.request.user
        return (serializer.save(created_by=user, last_modified_by=user))

    def perform_update(self, serializer):
        user = self.request.user
        return (serializer.save(last_modified_by=user))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if hasattr(instance, 'is_active'):
            instance.is_active = False
            instance.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return super().destroy(request, *args, **kwargs)


class DynamicListAPIView(ListAPIView):
    def get_serializer_context(self):
        context = super().get_serializer_context()
        fields_param = self.request.query_params.get('fields', None)
        if fields_param:
            context['fields'] = fields_param.split(',')
        return context

    pagination_class = None
