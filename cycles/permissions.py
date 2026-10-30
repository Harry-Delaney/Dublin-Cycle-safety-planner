from rest_framework import permissions


# Anyone can view a hazard, but only the person who reported it (or staff) can edit or delete it
class IsReporterOrReadOnly(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        # Viewing (GET, HEAD, OPTIONS) is always allowed
        if request.method in permissions.SAFE_METHODS:
            return True
        # Changes are allowed for staff or the original reporter
        return request.user.is_staff or obj.reported_by_id == request.user.id
